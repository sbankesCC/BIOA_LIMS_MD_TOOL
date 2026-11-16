"""Prompt builder: fills a prompt template's `{placeholders}` and returns text and image parts.

HTML comments (notes for developers) are removed. The template's order is kept, so its static
text stays first and the run's documents last. `{chunks}` becomes text parts with each scanned
page image as its own part, labeled with its chunk ID (CONTRACTS §1).
"""

import json
import re
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from app.config.business_rules import BusinessRules, RuleLine
from app.config.extraction_rules import ExtractionRules
from app.config.prompts import HTML_COMMENT_PATTERN, PLACEHOLDER_PATTERN, PromptTemplate
from app.contracts.chunk import Chunk
from app.contracts.extraction import ExcludedItem
from app.contracts.record import StoredRecord
from app.contracts.reference import ReferenceType
from app.llm.client import ImagePart, PromptPart, TextPart

CHUNKS_PLACEHOLDER = "chunks"

# Text of an empty list and of a field the judge gets no value for
NOTHING_TEXT = "(none)"
NOT_GIVEN_TEXT = "(not given)"

# Three or more line breaks (left where comments were removed) become one blank line
EXTRA_BLANK_LINES = re.compile(r"\n{3,}")

# The re-extraction section's fixed text, as the extraction prompt describes it
REEXTRACTION_HEADING = "# Problems to fix"
REEXTRACTION_INTRO = (
    "The previous extraction of these records had problems. Extract only these records and "
    "items again, following all rules above. For an existing record, return its record_id "
    "exactly as given (in place of record_ref). New items get a record_ref."
)


class PromptError(Exception):
    """Raised when a template needs a placeholder value the code did not give."""


class ReextractionProblem(BaseModel):
    """One problem to fix on re-extraction: an existing record (and field) or a missed item."""

    record_id: str | None = None
    item: str | None = None
    field: str | None = None
    problem: str
    chunk_ids: list[str] = []
    note: str | None = None


def build_prompt_parts(
    template: PromptTemplate, values: Mapping[str, str], chunks: Sequence[Chunk] = ()
) -> list[PromptPart]:
    """Fill the template's placeholders; `{chunks}` (if present) becomes text and image parts."""
    text = remove_comments(template.text)
    missing = set(PLACEHOLDER_PATTERN.findall(text)) - set(values) - {CHUNKS_PLACEHOLDER}
    if missing:
        raise PromptError(
            f"Prompt {template.name} needs values for {sorted(missing)}. Fill them in the code."
        )
    # One pass, so placeholder-like text inside a filled value is never replaced again
    filled = PLACEHOLDER_PATTERN.sub(lambda match: values.get(match[1], match[0]), text)
    before, marker, after = filled.partition("{" + CHUNKS_PLACEHOLDER + "}")
    parts: list[PromptPart] = [TextPart(text=before)]
    if marker:
        parts.extend(format_chunks(chunks))
        parts.append(TextPart(text=after))
    return merge_text_parts(parts)


def remove_comments(text: str) -> str:
    """Remove HTML comments and the blank lines they leave behind."""
    without_comments = HTML_COMMENT_PATTERN.sub("", text)
    return EXTRA_BLANK_LINES.sub("\n\n", without_comments).strip() + "\n"


def format_chunks(chunks: Sequence[Chunk]) -> list[PromptPart]:
    """Return `[chunk_id] text` per text chunk; a scanned page gets a label and its image."""
    parts: list[PromptPart] = []
    for chunk in chunks:
        if chunk.kind == "page_image" and chunk.image_ref is not None:
            parts.append(TextPart(text=f"\n[{chunk.chunk_id}] (scanned page image)\n"))
            parts.append(ImagePart(chunk_id=chunk.chunk_id, image_ref=chunk.image_ref))
        else:
            parts.append(TextPart(text=f"\n[{chunk.chunk_id}] {chunk.text or ''}\n"))
    return parts


def merge_text_parts(parts: Sequence[PromptPart]) -> list[PromptPart]:
    """Join neighbouring text parts, so images are the only breaks in the text."""
    merged: list[PromptPart] = []
    for part in parts:
        previous = merged[-1] if merged else None
        if isinstance(part, TextPart) and isinstance(previous, TextPart):
            merged[-1] = TextPart(text=previous.text + part.text)
        else:
            merged.append(part)
    return [part for part in merged if not isinstance(part, TextPart) or part.text]


def format_rule_lines(rules: Sequence[RuleLine]) -> str:
    """Return active rule lines as `- <ID> <text>`, without step, status or source."""
    lines = [f"- {rule.rule_id} {rule.text}" for rule in rules if rule.is_active]
    return "\n".join(lines) or NOTHING_TEXT


def build_general_rules(extraction_rules: ExtractionRules) -> str:
    """Return the active general extraction lines."""
    return format_rule_lines(extraction_rules.general)


def build_candidate_rules(extraction_rules: ExtractionRules) -> str:
    """Return the active candidate criteria."""
    return format_rule_lines(extraction_rules.candidates)


def build_field_section(business_rules: BusinessRules, extraction_rules: ExtractionRules) -> str:
    """Return one block per extracted or generated field: key, column and its guidance.

    The field's shape (key, column, one value or a list) comes from the business rules.
    """
    blocks: list[str] = []
    for field in business_rules.extracted_fields():
        list_note = " (a list: one entry per value)" if field.multi_value else ""
        heading = f"{field.key} ({field.column}){list_note}"
        blocks.append(f"{heading}\n{format_rule_lines(extraction_rules.rules_for(field.key))}")
    return "\n\n".join(blocks) or NOTHING_TEXT


def build_context_section(business_rules: BusinessRules, extraction_rules: ExtractionRules) -> str:
    """Return one block per context attribute: key and its guidance."""
    blocks = [
        f"{attribute.key}\n{format_rule_lines(extraction_rules.rules_for(attribute.key))}"
        for attribute in business_rules.context_fields()
    ]
    return "\n\n".join(blocks) or NOTHING_TEXT


def build_matching_rules(business_rules: BusinessRules, field_keys: Sequence[str]) -> str:
    """Return the active [Matching] lines of the fields that have items in the call."""
    rules = [
        rule
        for key in dict.fromkeys(field_keys)
        for rule in business_rules.rules_for("Matching", key)
    ]
    return format_rule_lines(rules)


def build_naming_rules(business_rules: BusinessRules) -> str:
    """Return every active [Naming] line."""
    return format_rule_lines(business_rules.rules_for("Naming"))


def build_checks(business_rules: BusinessRules) -> str:
    """Return every active [Plausibility] line."""
    return format_rule_lines(business_rules.rules_for("Plausibility"))


def build_rule_placeholders(
    business_rules: BusinessRules, extraction_rules: ExtractionRules
) -> dict[str, str]:
    """Return the four rule placeholders the extraction and verification prompts share.

    The guidance comes only from the extraction rules; the business rules give the field list.
    """
    return {
        "general_rules": build_general_rules(extraction_rules),
        "candidate_rules": build_candidate_rules(extraction_rules),
        "field_section": build_field_section(business_rules, extraction_rules),
        "context_section": build_context_section(business_rules, extraction_rules),
    }


def build_reextraction_section(
    records: Sequence[StoredRecord], problems: Sequence[ReextractionProblem]
) -> str:
    """Return the re-extraction section: the affected records and every problem to fix."""
    if not problems:
        return ""
    lines = [REEXTRACTION_HEADING, REEXTRACTION_INTRO, "", "Records to extract again:"]
    affected_ids = {problem.record_id for problem in problems if problem.record_id}
    for record in records:
        if record.record_id in affected_ids:
            found_in = ", ".join(record.found_in)
            summary = record.extraction.record_summary
            lines.append(f"- {record.record_id}: {summary} (found in {found_in})")
    lines += ["", "Problems:"]
    lines += [format_problem(problem) for problem in problems]
    return "\n".join(lines)


def format_problem(problem: ReextractionProblem) -> str:
    """Return one problem line: record or item, field, problem, chunk IDs and note."""
    subject = problem.record_id or f'item "{problem.item}"'
    field = f", field {problem.field}" if problem.field else ""
    chunks = f" ({', '.join(problem.chunk_ids)})" if problem.chunk_ids else ""
    note = f": {problem.note}" if problem.note else ""
    return f"- {subject}{field}: {problem.problem}{chunks}{note}"


def format_citation_results(records: Sequence[StoredRecord]) -> str:
    """Return one line per checked field: record ID, field key and citation result."""
    lines: list[str] = []
    for record in records:
        for key, stored in record.fields.items():
            if stored.verification is not None and stored.verification.citation_check:
                lines.append(f"- {record.record_id} {key}: {stored.verification.citation_check}")
    return "\n".join(lines) or NOTHING_TEXT


def format_records(records: Sequence[StoredRecord]) -> str:
    """Return each record as one JSON line: ID, where found, and each extracted field."""
    lines: list[str] = []
    for record in records:
        fields = {
            key: stored.extraction.model_dump(mode="json")
            for key, stored in record.fields.items()
            if stored.extraction is not None
        }
        data = {"record_id": record.record_id, "found_in": record.found_in, "fields": fields}
        lines.append(json.dumps(data, ensure_ascii=False))
    return "\n".join(lines) or NOTHING_TEXT


def format_excluded_items(items: Sequence[ExcludedItem]) -> str:
    """Return each excluded item as one JSON line."""
    lines = [json.dumps(item.model_dump(mode="json"), ensure_ascii=False) for item in items]
    return "\n".join(lines) or NOTHING_TEXT


def format_judge_record(values: Mapping[str, str | None], business_rules: BusinessRules) -> str:
    """Return the new record's identifying values, one line each with the column name."""
    columns = {field.key: field.column for field in business_rules.fields}
    lines = [
        f"- {columns.get(key, key)}: {value if value else NOT_GIVEN_TEXT}"
        for key, value in values.items()
    ]
    return "\n".join(lines)


def format_candidates(candidates: Sequence[ReferenceType]) -> str:
    """Return each shortlisted existing type as one JSON line, leaving out empty columns."""
    lines = [
        json.dumps(candidate.model_dump(mode="json", exclude_none=True), ensure_ascii=False)
        for candidate in candidates
    ]
    return "\n".join(lines) or NOTHING_TEXT
