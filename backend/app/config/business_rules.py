"""Business rules (`business_rules.md`): field definitions, rule lines and data tables.

The Markdown file is read in two stages: `read_markdown` keeps its raw parts (attribute tables,
rule lines, tables), then `build_business_rules` turns them into models once the checks in
`business_rules_checks.py` pass. Field order here is the column order of the DFD loader.
"""

import re
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

FILE_NAME = "business_rules.md"

# ----- Grammar: the words the file uses as structure, not as BioA data -----

RuleStatus = Literal["Confirmed", "Assumption", "Design", "Open"]
Step = Literal[
    "Extraction", "Normalization", "Matching", "Naming", "Assembly", "Validation", "Plausibility"
]
FieldRole = Literal["extracted", "derived", "generated", "context", "system", "blank_for_now"]
Requirement = Literal["required", "conditional", "optional"]
FieldType = Literal["text", "decimal", "integer", "boolean"]
DisallowedCharacters = Literal["greek_letters", "control_characters"]
GroupRule = Literal["one_of", "both_or_neither"]
SectionKind = Literal["general", "field", "business"]

STATUSES: tuple[str, ...] = get_args(RuleStatus)
STEPS: tuple[str, ...] = get_args(Step)
ROLES: tuple[str, ...] = get_args(FieldRole)
REQUIREMENTS: tuple[str, ...] = get_args(Requirement)
FIELD_TYPES: tuple[str, ...] = get_args(FieldType)
DISALLOWED_CHARACTERS: tuple[str, ...] = get_args(DisallowedCharacters)
GROUP_RULES: tuple[str, ...] = get_args(GroupRule)
INACTIVE_STATUS = "Open"
CONTEXT_ROLE = "context"

# Section headings (`## ...`) that code reads; every other section is prose for people
FIELD_PREFIX = "Field: "
GENERAL_PREFIX = "General rules"
BUSINESS_PREFIX = "Business rules"

# Attribute table keys, in the file's order
REQUIRED_ATTRIBUTES = ("Key", "Loader column", "Role", "Requirement", "Type")
OPTIONAL_ATTRIBUTES = (
    "Max length",
    "Lookup list",
    "Default",
    "Matching allowed",
    "Sent to duplicate judge",
    "Record name",
    "Multi-value separator",
    "Disallowed characters",
    "Drives",
)
ATTRIBUTE_HEADER = ["Attribute", "Value"]
NO_COLUMN = "none"
YES = "yes"
NO = "no"

# Table cells with a meaning of their own
ANY_VALUE = "any"
BLANK_PREFIX = "(blank"
ALL_LISTS = "(all lists)"
LIST_SEPARATOR = ";"
GROUP_FIELD_JOINER = "+"

# Table headings and columns code reads by name
STATUS_COLUMN = "Status"
ENTRY_COLUMN = "Entry"
LOOKUP_VALUE_COLUMN = "Lookup value"
REVIEWER_CHOOSES_COLUMN = "Reviewer chooses"
LOOKUP_LIST_COLUMN = "Lookup list"
VERSION_ROW = "Version"
CANDIDATE_HEADING = "Candidate criteria"
CONDITION_GROUPS_HEADING = "Condition groups"
EXCLUDED_VALUES_HEADING = "Excluded lookup values"
CONDITION_GROUP_COLUMNS = ("Group", "Rule", "Fields", "Issue code")

# Columns whose cells are row types or bookkeeping, not BioA values (see the no-literals test)
KEYWORD_COLUMNS = (
    ENTRY_COLUMN,
    "Match type",
    "Match",
    "Excluded from",
    STATUS_COLUMN,
    "Group",
    "Rule",
    "Issue code",
    "Unicode",
)

# Every word the file uses as structure. Some equal a loader column name (Status, Version); the
# no-client-literals test leaves these out, since they are grammar, not client data
GRAMMAR_WORDS = frozenset(
    {
        *REQUIRED_ATTRIBUTES,
        *OPTIONAL_ATTRIBUTES,
        *KEYWORD_COLUMNS,
        LOOKUP_VALUE_COLUMN,
        REVIEWER_CHOOSES_COLUMN,
        LOOKUP_LIST_COLUMN,
        VERSION_ROW,
        YES,
        NO,
        NO_COLUMN,
        ALL_LISTS,
    }
)

# `- <ID> [<Step>] <text> (<Status>[; <source>])`; the last parentheses hold status and source
RULE_LINE_PATTERN = re.compile(
    r"^- (?P<rule_id>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+) \[(?P<step>[A-Za-z]+)\] "
    r"(?P<text>.+) \((?P<status_text>[^()]*)\)$"
)
STATUS_WORD_PATTERN = re.compile(r"^(?P<word>[A-Za-z]+)\W*(?P<note>.*)$", re.DOTALL)
REQUIREMENT_PATTERN = re.compile(r"^(?P<word>[a-z_]+)(?:\s*\((?P<group>[a-z0-9_]+)\))?$")
TABLE_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")


# ----- Raw parts, as read from the Markdown -----


class RawTable(BaseModel):
    """One Markdown table: the `###` heading above it, header cells and row cells."""

    heading: str
    columns: list[str]
    rows: list[list[str]]
    line_number: int


class RawLine(BaseModel):
    """One bullet line in a parsed section, with the `###` heading it sits under."""

    text: str
    heading: str
    line_number: int


class RawSection(BaseModel):
    """One parsed `##` section: General rules, a field, or Business rules."""

    kind: SectionKind
    title: str
    line_number: int
    attribute_table: RawTable | None = None
    lines: list[RawLine] = []
    tables: list[RawTable] = []

    def attributes(self) -> dict[str, str]:
        """Return the attribute table as a key → value dict (empty if there is none)."""
        if self.attribute_table is None:
            return {}
        return {row[0]: row[1] for row in self.attribute_table.rows if len(row) >= 2}


class RawDocument(BaseModel):
    """The parts of `business_rules.md` that code reads."""

    version_table: RawTable | None = None
    sections: list[RawSection] = []

    def field_sections(self) -> list[RawSection]:
        """Return the `## Field:` sections, in file order."""
        return [section for section in self.sections if section.kind == "field"]


# ----- Models built from the raw parts -----


class RuleLine(BaseModel):
    """One rule line: ID, step tag, text, status and the note after the status."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    step: Step
    text: str
    status: RuleStatus
    note: str
    heading: str

    @property
    def is_active(self) -> bool:
        """Return True unless the rule is Open (Open rules are not acted on)."""
        return self.status != INACTIVE_STATUS


class RuleTable(BaseModel):
    """One data table: its `###` heading, columns, and rows as column → cell dicts."""

    heading: str
    columns: list[str]
    rows: list[dict[str, str]]

    def active_rows(self) -> list[dict[str, str]]:
        """Return the rows whose Status is not Open (all rows if there is no Status column)."""
        return [row for row in self.rows if not is_open_status(row.get(STATUS_COLUMN, ""))]


class RuleOwner(BaseModel):
    """What fields and context attributes share: key, role, requirement, type, rules, tables."""

    key: str
    role: FieldRole
    requirement: Requirement
    condition_group: str | None = None
    type: FieldType
    rules: list[RuleLine] = []
    tables: list[RuleTable] = []


class FieldDefinition(RuleOwner):
    """One loader field: its DFD column, role, requirement, type, limits and flags."""

    column: str
    max_length: int | None = Field(default=None, gt=0)
    lookup_sheet: str | None = None
    default: str | None = None
    matching_allowed: bool = False
    sent_to_duplicate_judge: bool = False
    is_record_name: bool = False
    separator: str | None = None
    disallowed_characters: list[DisallowedCharacters] = []

    @property
    def multi_value(self) -> bool:
        """Return True if the field holds several values (it has a multi-value separator)."""
        return self.separator is not None

    @property
    def is_extracted(self) -> bool:
        """Return True if the model extracts this field (role extracted or generated)."""
        return self.role in ("extracted", "generated")


class ContextAttribute(RuleOwner):
    """One context attribute: extracted for other rules, never exported; drives one field."""

    drives: str


class RuleSection(BaseModel):
    """The rule lines and tables of the General rules or the Business rules section."""

    rules: list[RuleLine] = []
    tables: list[RuleTable] = []


class OneOfGroup(BaseModel):
    """Condition group: at least one option (a set of fields) must be completely filled."""

    model_config = ConfigDict(extra="forbid")

    rule: Literal["one_of"]
    options: list[list[str]] = Field(min_length=2)
    issue_code: str


class BothOrNeitherGroup(BaseModel):
    """Condition group: the fields are either all filled or all empty."""

    model_config = ConfigDict(extra="forbid")

    rule: Literal["both_or_neither"]
    fields: list[str] = Field(min_length=2)
    issue_code: str


ConditionGroup = Annotated[OneOfGroup | BothOrNeitherGroup, Field(discriminator="rule")]


class BusinessRules(BaseModel):
    """The whole business rules file: loader fields, context attributes, rules and tables."""

    version: str = Field(min_length=1)
    fields: list[FieldDefinition] = Field(min_length=1)
    context: list[ContextAttribute] = []
    general: RuleSection = RuleSection()
    business: RuleSection = RuleSection()
    condition_groups: dict[str, ConditionGroup] = {}

    def extracted_fields(self) -> list[FieldDefinition]:
        """Return the fields the model extracts (extracted and generated), in loader order."""
        return [field for field in self.fields if field.is_extracted]

    def derived_fields(self) -> list[FieldDefinition]:
        """Return the fields Assembly derives from other values, in loader order."""
        return [field for field in self.fields if field.role == "derived"]

    def context_fields(self) -> list[ContextAttribute]:
        """Return the context attributes, in file order."""
        return list(self.context)

    def columns(self) -> list[str]:
        """Return the DFD column names in loader order."""
        return [field.column for field in self.fields]

    def record_name_field(self) -> FieldDefinition:
        """Return the field marked `Record name` (the checks make sure exactly one is)."""
        return next(field for field in self.fields if field.is_record_name)

    def duplicate_judge_fields(self) -> list[FieldDefinition]:
        """Return the fields sent to the duplicate judge (and its cache key), in loader order."""
        return [field for field in self.fields if field.sent_to_duplicate_judge]

    def owners(self) -> list[RuleOwner]:
        """Return every field and context attribute, fields first."""
        return [*self.fields, *self.context]

    def all_rules(self) -> list[RuleLine]:
        """Return every rule line: general, then each field and attribute, then business."""
        owner_rules = [rule for owner in self.owners() for rule in owner.rules]
        return [*self.general.rules, *owner_rules, *self.business.rules]

    def rules_for(
        self, step: Step, field: str | None = None, active_only: bool = True
    ) -> list[RuleLine]:
        """Return the rule lines tagged `step`: all of them, or only one field's."""
        rules = self.all_rules() if field is None else self.find_owner(field).rules
        return [rule for rule in rules if rule.step == step and (rule.is_active or not active_only)]

    def table(self, field_or_section: str, heading: str) -> RuleTable:
        """Return the table under `### heading` of a field key, or of "general" / "business"."""
        if field_or_section == "general":
            tables = self.general.tables
        elif field_or_section == "business":
            tables = self.business.tables
        else:
            tables = self.find_owner(field_or_section).tables
        for table in tables:
            if table.heading == heading:
                return table
        raise KeyError(f"{FILE_NAME}: '{field_or_section}' has no table '### {heading}'.")

    def find_owner(self, key: str) -> RuleOwner:
        """Return the field or context attribute with this key."""
        for owner in self.owners():
            if owner.key == key:
                return owner
        raise KeyError(f"{FILE_NAME}: there is no field or context attribute '{key}'.")


# ----- Small helpers for cells and status text -----


def split_status(status_text: str) -> tuple[str, str]:
    """Split a status into its first word (the label) and the note after it."""
    match = STATUS_WORD_PATTERN.match(status_text.strip())
    if match is None:
        return "", status_text.strip()
    return match["word"], match["note"].strip()


def is_open_status(status_text: str) -> bool:
    """Return True if a status cell or rule status starts with Open."""
    return split_status(status_text)[0] == INACTIVE_STATUS


def is_blank_cell(value: str) -> bool:
    """Return True for an empty cell or a `(blank ...)` cell: the output is left blank."""
    return not value or value.startswith(BLANK_PREFIX)


def split_list_cell(value: str) -> list[str]:
    """Split a `;`-separated cell into its trimmed, non-empty parts."""
    return [part.strip() for part in value.split(LIST_SEPARATOR) if part.strip()]


def split_table_row(line: str) -> list[str]:
    """Split one Markdown table line into its trimmed cells."""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


# ----- Stage 1: read the Markdown into raw parts -----


class MarkdownReader:
    """Walk the file line by line, collecting tables and bullet lines per `##` section."""

    def __init__(self) -> None:
        """Start before the first `##` section."""
        self.document = RawDocument()
        self.section: RawSection | None = None
        self.is_before_sections = True
        self.heading = ""
        self.table_lines: list[tuple[int, str]] = []

    def read(self, text: str) -> RawDocument:
        """Read the whole file and return its raw parts."""
        for line_number, line in enumerate(text.splitlines(), start=1):
            self.read_line(line_number, line.strip())
        self.finish_table()
        return self.document

    def read_line(self, line_number: int, line: str) -> None:
        """Route one line: table row, `##` section, `###` heading, or bullet line."""
        if line.startswith("|"):
            self.table_lines.append((line_number, line))
            return
        self.finish_table()
        if line.startswith("### "):
            self.heading = line[4:].strip()
        elif line.startswith("## "):
            self.start_section(line_number, line[3:].strip())
        elif line.startswith("- ") and self.section is not None:
            self.section.lines.append(
                RawLine(text=line, heading=self.heading, line_number=line_number)
            )

    def start_section(self, line_number: int, title: str) -> None:
        """Start a new `##` section; only General rules, fields and Business rules are kept."""
        self.is_before_sections = False
        self.heading = ""
        kind = section_kind(title)
        if kind is None:
            self.section = None
            return
        self.section = RawSection(kind=kind, title=title, line_number=line_number)
        self.document.sections.append(self.section)

    def finish_table(self) -> None:
        """Turn the collected table lines into a table and file it where it belongs."""
        if not self.table_lines:
            return
        table = build_raw_table(self.heading, self.table_lines)
        self.table_lines = []
        # The first table of the file (before any section) holds the version
        if self.is_before_sections:
            self.document.version_table = self.document.version_table or table
        elif self.section is None:
            return
        elif not self.heading and table.columns == ATTRIBUTE_HEADER:
            self.section.attribute_table = table
        else:
            self.section.tables.append(table)


def section_kind(title: str) -> SectionKind | None:
    """Return the kind of a `##` section from its title, or None for a prose section."""
    if title.startswith(FIELD_PREFIX):
        return "field"
    if title.startswith(GENERAL_PREFIX):
        return "general"
    if title.startswith(BUSINESS_PREFIX):
        return "business"
    return None


def build_raw_table(heading: str, lines: list[tuple[int, str]]) -> RawTable:
    """Build a raw table: the first line is the header; the `---` line is skipped."""
    first_line_number, header_line = lines[0]
    rows = [split_table_row(line) for _, line in lines[1:]]
    rows = [row for row in rows if not all(TABLE_SEPARATOR_CELL.match(cell) for cell in row)]
    return RawTable(
        heading=heading,
        columns=split_table_row(header_line),
        rows=rows,
        line_number=first_line_number,
    )


def read_markdown(text: str) -> RawDocument:
    """Read `business_rules.md` text into its raw parts (no checks yet)."""
    return MarkdownReader().read(text)


def read_version(document: RawDocument) -> str | None:
    """Return the Version row of the file's first table, or None if there is none."""
    if document.version_table is None:
        return None
    for row in document.version_table.rows:
        if len(row) >= 2 and row[0] == VERSION_ROW and row[1]:
            return row[1]
    return None


# ----- Stage 2: build the models (the raw checks have passed) -----


def build_business_rules(document: RawDocument) -> BusinessRules:
    """Build the business rules model from raw parts that passed the raw checks."""
    fields: list[FieldDefinition] = []
    context: list[ContextAttribute] = []
    for section in document.field_sections():
        attributes = section.attributes()
        if attributes["Role"] == CONTEXT_ROLE:
            context.append(build_context_attribute(section, attributes))
        else:
            fields.append(build_field(section, attributes))
    business = build_rule_section(document, "business")
    return BusinessRules(
        version=read_version(document) or "",
        fields=fields,
        context=context,
        general=build_rule_section(document, "general"),
        business=business,
        condition_groups=build_condition_groups(business),
    )


def build_field(section: RawSection, attributes: dict[str, str]) -> FieldDefinition:
    """Build one loader field from its attribute table, rule lines and tables."""
    separator = attributes.get("Multi-value separator")
    max_length = attributes.get("Max length")
    return FieldDefinition.model_validate(
        {
            **build_owner_values(section, attributes),
            "column": attributes["Loader column"],
            "max_length": int(max_length) if max_length else None,
            "lookup_sheet": attributes.get("Lookup list") or None,
            "default": attributes.get("Default") or None,
            "matching_allowed": attributes.get("Matching allowed") == YES,
            "sent_to_duplicate_judge": attributes.get("Sent to duplicate judge") == YES,
            "is_record_name": attributes.get("Record name") == YES,
            "separator": separator.strip('"') if separator else None,
            "disallowed_characters": split_list_cell(attributes.get("Disallowed characters", "")),
        }
    )


def build_context_attribute(section: RawSection, attributes: dict[str, str]) -> ContextAttribute:
    """Build one context attribute from its attribute table, rule lines and tables."""
    return ContextAttribute.model_validate(
        {**build_owner_values(section, attributes), "drives": attributes["Drives"]}
    )


def build_owner_values(section: RawSection, attributes: dict[str, str]) -> dict[str, object]:
    """Return the values every field and context attribute has, read from its section."""
    requirement = REQUIREMENT_PATTERN.match(attributes["Requirement"])
    if requirement is None:
        raise ValueError(f"{FILE_NAME}: unreadable Requirement in '{section.title}'.")
    return {
        "key": attributes["Key"],
        "role": attributes["Role"],
        "requirement": requirement["word"],
        "condition_group": requirement["group"],
        "type": attributes["Type"],
        "rules": [build_rule_line(line) for line in section.lines],
        "tables": [build_table(table) for table in section.tables],
    }


def build_rule_section(document: RawDocument, kind: SectionKind) -> RuleSection:
    """Build the rule lines and tables of every section of one kind (general or business)."""
    sections = [section for section in document.sections if section.kind == kind]
    return RuleSection(
        rules=[build_rule_line(line) for section in sections for line in section.lines],
        tables=[build_table(table) for section in sections for table in section.tables],
    )


def build_rule_line(line: RawLine) -> RuleLine:
    """Build one rule line from a bullet the raw checks accepted."""
    match = RULE_LINE_PATTERN.match(line.text)
    if match is None:
        raise ValueError(f"{FILE_NAME}: line {line.line_number} is not a rule line.")
    status, note = split_status(match["status_text"])
    return RuleLine.model_validate(
        {
            "rule_id": match["rule_id"],
            "step": match["step"],
            "text": match["text"].strip(),
            "status": status,
            "note": note,
            "heading": line.heading,
        }
    )


def build_table(table: RawTable) -> RuleTable:
    """Build a data table with each row as a column → cell dict."""
    rows = [dict(zip(table.columns, row, strict=False)) for row in table.rows]
    return RuleTable(heading=table.heading, columns=table.columns, rows=rows)


def build_condition_groups(business: RuleSection) -> dict[str, ConditionGroup]:
    """Build the condition groups from the active rows of the Condition groups table."""
    tables = [table for table in business.tables if table.heading == CONDITION_GROUPS_HEADING]
    groups: dict[str, ConditionGroup] = {}
    for table in tables:
        for row in table.active_rows():
            groups[row["Group"]] = build_condition_group(row)
    return groups


def build_condition_group(row: dict[str, str]) -> ConditionGroup:
    """Build one group: `;` separates options (or fields), `+` joins fields in an option."""
    parts = split_list_cell(row["Fields"])
    if row["Rule"] == "one_of":
        options = [[key.strip() for key in part.split(GROUP_FIELD_JOINER)] for part in parts]
        return OneOfGroup(rule="one_of", options=options, issue_code=row["Issue code"])
    return BothOrNeitherGroup(rule="both_or_neither", fields=parts, issue_code=row["Issue code"])


def fields_in_group(group: OneOfGroup | BothOrNeitherGroup) -> list[str]:
    """Return every field key a condition group uses."""
    if isinstance(group, OneOfGroup):
        return [key for option in group.options for key in option]
    return list(group.fields)
