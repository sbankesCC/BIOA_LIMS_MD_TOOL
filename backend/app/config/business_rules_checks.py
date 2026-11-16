"""Startup checks for `business_rules.md`, and the loader that runs them.

Raw checks run on the file's raw parts before models are built; model checks run on the built
rules; cross-file checks compare the rules with the lookup lists, DFD template and catalogue.
Each check returns plain-language problems; any problem stops the app from starting.
"""

import re
from pathlib import Path

from pydantic import ValidationError

from app.config.business_rules import (
    ALL_LISTS,
    ATTRIBUTE_HEADER,
    CANDIDATE_HEADING,
    CONDITION_GROUP_COLUMNS,
    CONDITION_GROUPS_HEADING,
    CONTEXT_ROLE,
    DISALLOWED_CHARACTERS,
    ENTRY_COLUMN,
    EXCLUDED_VALUES_HEADING,
    FIELD_TYPES,
    FILE_NAME,
    GROUP_RULES,
    KEYWORD_COLUMNS,
    LOOKUP_LIST_COLUMN,
    LOOKUP_VALUE_COLUMN,
    NO,
    NO_COLUMN,
    OPTIONAL_ATTRIBUTES,
    REQUIRED_ATTRIBUTES,
    REQUIREMENT_PATTERN,
    REQUIREMENTS,
    REVIEWER_CHOOSES_COLUMN,
    ROLES,
    RULE_LINE_PATTERN,
    STATUS_COLUMN,
    STATUSES,
    STEPS,
    YES,
    BusinessRules,
    RawDocument,
    RawTable,
    RuleTable,
    build_business_rules,
    fields_in_group,
    find_referenced_table,
    is_blank_cell,
    is_keyword_cell,
    read_markdown,
    read_version,
    split_list_cell,
    split_status,
)
from app.config.dfd_template import DfdTemplate
from app.config.errors import ConfigError, describe_validation_problem, require_file
from app.config.issue_catalogue import IssueCatalogue
from app.config.lookup_lists import LookupLists

# Field keys are snake_case: they appear in every contract and JSON Schema
FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
YES_NO_ATTRIBUTES = ("Matching allowed", "Sent to duplicate judge", "Record name")


# ----- Loading -----


def load_business_rules(path: Path) -> BusinessRules:
    """Load `business_rules.md` and check it on its own; raise ConfigError on any problem."""
    require_file(path)
    return parse_business_rules(path.read_text(encoding="utf-8"))


def parse_business_rules(text: str) -> BusinessRules:
    """Read the file text, run the raw checks, build the models, then run the model checks."""
    document = read_markdown(text)
    raw_problems = (
        find_version_problems(document)
        + find_attribute_problems(document)
        + find_rule_line_problems(document)
        + find_table_problems(document)
    )
    if raw_problems:
        raise ConfigError(raw_problems)
    # The raw checks should catch everything; this keeps any gap a plain ConfigError
    try:
        rules = build_business_rules(document)
    except ValidationError as error:
        problems = [describe_validation_problem(FILE_NAME, item) for item in error.errors()]
        raise ConfigError(problems) from error
    model_problems = (
        find_duplicate_id_problems(rules)
        + find_record_name_problems(rules)
        + find_extraction_rule_problems(rules)
        + find_rule_placement_problems(rules)
        + find_reference_problems(rules)
        + find_table_reference_problems(rules)
    )
    if model_problems:
        raise ConfigError(model_problems)
    return rules


# ----- Raw checks -----


def find_version_problems(document: RawDocument) -> list[str]:
    """Check the first table has a Version row and the file has field sections."""
    problems: list[str] = []
    if read_version(document) is None:
        problems.append(f"{FILE_NAME}: the first table needs a 'Version' row with a value.")
    if not document.field_sections():
        problems.append(f"{FILE_NAME}: no '## Field: <name>' sections were found.")
    return problems


def find_attribute_problems(document: RawDocument) -> list[str]:
    """Check each field's attribute table: keys present and known, values from allowed sets."""
    problems: list[str] = []
    for section in document.field_sections():
        name = f"{FILE_NAME}: '## {section.title}'"
        if section.attribute_table is None:
            problems.append(f"{name} has no 'Attribute | Value' table under its heading.")
            continue
        # A malformed or repeated row would otherwise be read silently
        table_problems = find_attribute_table_problems(name, section.attribute_table)
        if table_problems:
            problems += table_problems
            continue
        attributes = section.attributes()
        missing = [key for key in REQUIRED_ATTRIBUTES if not attributes.get(key)]
        unknown = [
            key for key in attributes if key not in REQUIRED_ATTRIBUTES + OPTIONAL_ATTRIBUTES
        ]
        problems += [f"{name} is missing the attribute '{key}'." for key in missing]
        problems += [f"{name} has an unknown attribute '{key}'." for key in unknown]
        if not missing:
            problems += find_attribute_value_problems(name, attributes)
    return problems


def find_attribute_table_problems(name: str, table: RawTable) -> list[str]:
    """Check an attribute table: two cells per row, and each attribute named once."""
    problems = [
        f"{name}: the attribute row '{' | '.join(row)}' has {len(row)} cells; it needs "
        f"{len(ATTRIBUTE_HEADER)} (Attribute | Value). Write a '|' inside a value as '\\|'."
        for row in table.rows
        if len(row) != len(ATTRIBUTE_HEADER)
    ]
    keys = [row[0] for row in table.rows]
    problems += [
        f"{name}: the attribute '{key}' is listed twice. Keep one row." for key in repeated(keys)
    ]
    return problems


def find_attribute_value_problems(name: str, attributes: dict[str, str]) -> list[str]:
    """Check one field's attribute values: role, requirement, type, numbers, flags, column."""
    problems: list[str] = []
    requirement = REQUIREMENT_PATTERN.match(attributes["Requirement"])
    # Each value must come from its allowed set, so code never guesses what it means
    problems += find_key_problems(name, attributes["Key"])
    problems += not_in_set(name, "Role", attributes["Role"], ROLES)
    problems += not_in_set(name, "Type", attributes["Type"], FIELD_TYPES)
    requirement_word = requirement["word"] if requirement else attributes["Requirement"]
    problems += not_in_set(name, "Requirement", requirement_word, REQUIREMENTS)
    # Only a conditional requirement names a group; anywhere else it would be ignored
    if requirement and requirement["group"] and requirement_word != "conditional":
        problems.append(
            f"{name}: 'Requirement' is '{attributes['Requirement']}', but only 'conditional' "
            "names a group. Remove the group or make the field conditional."
        )
    for key in YES_NO_ATTRIBUTES:
        if key in attributes:
            problems += not_in_set(name, key, attributes[key], (YES, NO))
    for value in split_list_cell(attributes.get("Disallowed characters", "")):
        problems += not_in_set(name, "Disallowed characters", value, DISALLOWED_CHARACTERS)
    max_length = attributes.get("Max length")
    if max_length is not None and not (max_length.isdigit() and int(max_length) > 0):
        problems.append(f"{name}: 'Max length' must be a whole number above 0.")
    problems += find_context_attribute_problems(name, attributes)
    return problems


def find_context_attribute_problems(name: str, attributes: dict[str, str]) -> list[str]:
    """Check the loader column and Drives fit the role: context attributes only, and always."""
    is_context = attributes["Role"] == CONTEXT_ROLE
    problems: list[str] = []
    if is_context and attributes["Loader column"] != NO_COLUMN:
        problems.append(f"{name} is a context attribute, so its 'Loader column' must be none.")
    if not is_context and attributes["Loader column"] == NO_COLUMN:
        problems.append(f"{name} is a loader field, so it needs a 'Loader column' name.")
    if is_context and not attributes.get("Drives"):
        problems.append(f"{name} is a context attribute, so it needs 'Drives' (a field key).")
    if not is_context and "Drives" in attributes:
        problems.append(f"{name} has 'Drives', which only context attributes may have.")
    return problems


def not_in_set(name: str, key: str, value: str, allowed: tuple[str, ...]) -> list[str]:
    """Return a problem if `value` is not one of `allowed`."""
    if value in allowed:
        return []
    return [f"{name}: '{key}' is '{value}'; use one of: {', '.join(allowed)}."]


def find_key_problems(name: str, key: str) -> list[str]:
    """Return a problem if a field key is not snake_case."""
    if FIELD_KEY_PATTERN.match(key):
        return []
    return [f"{name}: 'Key' is '{key}'; use snake_case (lower case letters, digits, _)."]


def find_rule_line_problems(document: RawDocument) -> list[str]:
    """Check every bullet in a parsed section is a rule line with a known step and status."""
    problems: list[str] = []
    for section in document.sections:
        for line in section.lines:
            where = f"{FILE_NAME}: line {line.line_number}"
            match = RULE_LINE_PATTERN.match(line.text)
            if match is None:
                problems.append(
                    f"{where} is not a rule line. Write it as "
                    "'- <ID> [<Step>] <text> (<Status>; <source>)'."
                )
                continue
            problems += not_in_set(where, "step", match["step"], STEPS)
            status = split_status(match["status_text"])[0]
            problems += not_in_set(where, "status", status, STATUSES)
        problems += [
            f"{FILE_NAME}: line {line.line_number} is not read. Start each rule line with '- ' "
            "at the start of the line, and keep the whole rule on that one line."
            for line in section.stray_lines
        ]
    return problems


def find_table_problems(document: RawDocument) -> list[str]:
    """Check table rows have one cell per column, Status cells are known, groups are readable."""
    problems: list[str] = []
    for section in document.sections:
        for table in section.tables:
            problems += find_table_shape_problems(table)
            if table.heading == CONDITION_GROUPS_HEADING:
                problems += find_condition_table_problems(table)
    return problems


def find_table_shape_problems(table: RawTable) -> list[str]:
    """Check one table: same number of cells as columns, and a known label in each Status."""
    problems: list[str] = []
    where = f"{FILE_NAME}: table '### {table.heading}' (line {table.line_number})"
    for row in table.rows:
        if len(row) != len(table.columns):
            problems.append(
                f"{where}: a row has {len(row)} cells, the header has {len(table.columns)}."
            )
            continue
        if STATUS_COLUMN in table.columns:
            status = split_status(row[table.columns.index(STATUS_COLUMN)])[0]
            problems += not_in_set(where, STATUS_COLUMN, status, STATUSES)
    return problems


def find_condition_table_problems(table: RawTable) -> list[str]:
    """Check the Condition groups table has its columns and each Rule is a known group rule."""
    where = f"{FILE_NAME}: table '### {CONDITION_GROUPS_HEADING}'"
    missing = [column for column in CONDITION_GROUP_COLUMNS if column not in table.columns]
    if missing:
        return [f"{where} is missing the columns {', '.join(missing)}."]
    # Rows with the wrong cell count are reported by the shape check
    rows = [
        dict(zip(table.columns, row, strict=True))
        for row in table.rows
        if len(row) == len(table.columns)
    ]
    problems: list[str] = []
    for row in rows:
        problems += not_in_set(where, "Rule", row["Rule"], GROUP_RULES)
        # Each group compares at least two options (one_of) or two fields (both_or_neither)
        if len(split_list_cell(row["Fields"])) < 2:
            problems.append(
                f"{where}: group '{row['Group']}' needs at least two entries in 'Fields', "
                "separated by ';'."
            )
    problems += [
        f"{where}: group '{name}' is listed twice. Give each group its own name."
        for name in repeated([row["Group"] for row in rows])
    ]
    return problems


# ----- Model checks -----


def find_duplicate_id_problems(rules: BusinessRules) -> list[str]:
    """Check rule IDs, table entry IDs, field keys and loader columns are each unique."""
    rule_ids = [rule.rule_id for rule in rules.all_rules()]
    entry_ids = [
        row[ENTRY_COLUMN]
        for table in all_tables(rules)
        if ENTRY_COLUMN in table.columns
        for row in table.rows
    ]
    keys = [owner.key for owner in rules.owners()]
    problems = [f"{FILE_NAME}: rule ID {value} is used twice." for value in repeated(rule_ids)]
    problems += [
        f"{FILE_NAME}: table entry {value} is used twice." for value in repeated(entry_ids)
    ]
    problems += [f"{FILE_NAME}: field key '{value}' is used twice." for value in repeated(keys)]
    problems += [
        f"{FILE_NAME}: loader column '{value}' is used twice."
        for value in repeated(rules.columns())
    ]
    return problems


def repeated(values: list[str]) -> list[str]:
    """Return each value that appears more than once, in first-seen order."""
    seen: set[str] = set()
    found: list[str] = []
    for value in values:
        if value in seen and value not in found:
            found.append(value)
        seen.add(value)
    return found


def find_record_name_problems(rules: BusinessRules) -> list[str]:
    """Check exactly one field is the record name, and it is sent to the duplicate judge."""
    name_fields = [field for field in rules.fields if field.is_record_name]
    if len(name_fields) != 1:
        return [
            f"{FILE_NAME}: exactly one field must have 'Record name | yes', but "
            f"{len(name_fields)} do. Mark the field that names a record, and only that one."
        ]
    if not name_fields[0].sent_to_duplicate_judge:
        return [
            f"{FILE_NAME}: field '{name_fields[0].key}' is the record name but is not sent to "
            "the duplicate judge. Add 'Sent to duplicate judge | yes' to it."
        ]
    return []


def find_extraction_rule_problems(rules: BusinessRules) -> list[str]:
    """Check each extracted field and context attribute has an active [Extraction] line.

    Those lines are the model's only instructions for the field.
    """
    owners = [*rules.extracted_fields(), *rules.context]
    return [
        f"{FILE_NAME}: '{owner.key}' is extracted but has no active [Extraction] rule line. "
        "Add one that says what to copy from the documents."
        for owner in owners
        if not rules.rules_for("Extraction", owner.key)
    ]


def find_rule_placement_problems(rules: BusinessRules) -> list[str]:
    """Check rule lines sit where a prompt reads them, so none is silently left out.

    Business [Extraction] lines are read only under Candidate criteria, and [Matching] lines
    only from field sections.
    """
    problems = [
        f"{FILE_NAME}: rule {rule.rule_id} is an [Extraction] line under '### {rule.heading}', "
        f"but only '### {CANDIDATE_HEADING}' lines reach the extraction prompt. Move it there."
        for rule in rules.business.rules
        if rule.step == "Extraction" and rule.heading != CANDIDATE_HEADING
    ]
    section_rules = [*rules.general.rules, *rules.business.rules]
    problems += [
        f"{FILE_NAME}: rule {rule.rule_id} is a [Matching] line outside a field section, so "
        "no prompt reads it. Move it to the field it is about."
        for rule in section_rules
        if rule.step == "Matching"
    ]
    return problems


def find_reference_problems(rules: BusinessRules) -> list[str]:
    """Check Drives values, condition group fields and requirement groups name real things."""
    field_keys = {field.key for field in rules.fields}
    problems = [
        f"{FILE_NAME}: context attribute '{attribute.key}' drives '{attribute.drives}', "
        "which is not a loader field key."
        for attribute in rules.context
        if attribute.drives not in field_keys
    ]
    for group_name, group in rules.condition_groups.items():
        problems += [
            f"{FILE_NAME}: condition group '{group_name}' names unknown field '{key}'."
            for key in fields_in_group(group)
            if key not in field_keys
        ]
    for field in rules.fields:
        if (
            field.requirement == "conditional"
            and field.condition_group not in rules.condition_groups
        ):
            problems.append(
                f"{FILE_NAME}: field '{field.key}' is conditional but names no active condition "
                "group. Write it as 'conditional (<group>)' with a group from the Condition "
                "groups table."
            )
    return problems


def find_table_reference_problems(rules: BusinessRules) -> list[str]:
    """Check each `in <table>` cell of a derivation input column names a table of its section."""
    problems: list[str] = []
    input_columns = rules.input_columns()
    for tables in rules.table_groups():
        headings = {table.heading for table in tables}
        for table in tables:
            # Only input columns hold `in` cells; other columns may hold words such as "in fridge"
            cells = [
                row[column]
                for row in table.rows
                for column in table.columns
                if column in input_columns
            ]
            problems += [
                f"{FILE_NAME}: '### {table.heading}': the cell '{cell}' names no table "
                f"'### {heading}' in the same section. Fix the name or add that table."
                for cell in cells
                if (heading := find_referenced_table(cell)) is not None and heading not in headings
            ]
    return problems


def all_tables(rules: BusinessRules) -> list[RuleTable]:
    """Return every data table in the file."""
    owner_tables = [table for owner in rules.owners() for table in owner.tables]
    return [*rules.general.tables, *owner_tables, *rules.business.tables]


# ----- Cross-file checks (called by the config bundle) -----


def find_lookup_list_problems(rules: BusinessRules, lookup_lists: LookupLists) -> list[str]:
    """Check every lookup list the file names is a sheet of the lookup value list."""
    sheets = lookup_lists.sheets
    named = [(field.key, field.lookup_sheet) for field in rules.fields if field.lookup_sheet]
    excluded = find_excluded_values_table(rules)
    if excluded is not None:
        named += [
            (EXCLUDED_VALUES_HEADING, row[LOOKUP_LIST_COLUMN])
            for row in excluded.active_rows()
            if row[LOOKUP_LIST_COLUMN] != ALL_LISTS
        ]
    return [
        f"lookup_lists.xlsx: the sheet '{sheet}' named by '{owner}' in {FILE_NAME} is missing."
        for owner, sheet in named
        if sheet not in sheets
    ]


def find_excluded_values_table(rules: BusinessRules) -> RuleTable | None:
    """Return the Excluded lookup values table of the General rules, if there is one."""
    tables = [table for table in rules.general.tables if table.heading == EXCLUDED_VALUES_HEADING]
    return tables[0] if tables else None


def find_lookup_value_problems(rules: BusinessRules, lookup_lists: LookupLists) -> list[str]:
    """Check defaults, translation targets and table outputs are on their lookup lists."""
    lists_by_column = {
        field.column: lookup_lists.sheets.get(field.lookup_sheet, [])
        for field in rules.fields
        if field.lookup_sheet
    }
    problems: list[str] = []
    for field in rules.fields:
        if field.lookup_sheet and field.default:
            problems += off_list(
                field.key, "Default", [field.default], lists_by_column[field.column]
            )
        for table in field.tables:
            problems += find_translation_problems(field.key, field.column, table, lists_by_column)
    for table in all_tables(rules):
        problems += find_table_column_problems(table, lists_by_column)
    return problems


def find_translation_problems(
    key: str, column: str, table: RuleTable, lists_by_column: dict[str, list[str]]
) -> list[str]:
    """Check a field table's 'Lookup value' and 'Reviewer chooses' cells are on its list."""
    allowed = lists_by_column.get(column)
    if allowed is None:
        return []
    values: list[str] = []
    for row in table.active_rows():
        values += [row.get(LOOKUP_VALUE_COLUMN, "")]
        values += split_list_cell(row.get(REVIEWER_CHOOSES_COLUMN, ""))
    where = f"'### {table.heading}' of '{key}'"
    return off_list(where, LOOKUP_VALUE_COLUMN, values, allowed)


def find_table_column_problems(
    table: RuleTable, lists_by_column: dict[str, list[str]]
) -> list[str]:
    """Check every cell in a column named after a lookup field is on that field's list."""
    problems: list[str] = []
    for column in table.columns:
        allowed = lists_by_column.get(column)
        # Keyword columns (such as Status) hold bookkeeping, not field values
        if allowed is None or column in KEYWORD_COLUMNS:
            continue
        values = [row.get(column, "") for row in table.active_rows()]
        problems += off_list(f"'### {table.heading}'", column, values, allowed)
    return problems


def off_list(where: str, column: str, values: list[str], allowed: list[str]) -> list[str]:
    """Return a problem per value not on the list; blank cells and `any` are allowed."""
    return [
        f"{FILE_NAME}: {where}: '{column}' value '{value}' is not on its lookup list. "
        "Fix the value or add it to lookup_lists.xlsx."
        for value in values
        if not is_blank_cell(value) and not is_keyword_cell(value) and value not in allowed
    ]


def find_template_problems(rules: BusinessRules, template: DfdTemplate) -> list[str]:
    """Check the DFD template headers equal the loader columns, in the same order."""
    columns = rules.columns()
    if template.headers == columns:
        return []
    return [
        f"dfd_template.xlsx: the headers do not match the loader columns in {FILE_NAME} "
        f"(template has {len(template.headers)}, {FILE_NAME} has {len(columns)}). "
        "They must be the same names in the same order."
    ]


def find_issue_code_problems(rules: BusinessRules, catalogue: IssueCatalogue) -> list[str]:
    """Check every condition group's issue code is a record issue in the catalogue."""
    return [
        f"{FILE_NAME}: condition group '{group_name}' uses issue code {group.issue_code}, "
        "which is not a record issue in issue_catalogue.yaml."
        for group_name, group in rules.condition_groups.items()
        if group.issue_code not in catalogue.record_issues
    ]
