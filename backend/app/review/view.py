"""Flattened review view (CONTRACTS §13 `GET /runs/{run_id}/records`): one row per record.

Each cell has its value, display value, the value as written, origin, color, issues, sources
and alternatives. Fields with role `blank_for_now` show the config's placeholder value; they
stay empty in the record and the loader. Sources are locations only, never chunk text.
"""

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ValidationError

from app.config.field_rules import FieldRule, FieldRules
from app.contracts.chunk import Chunk
from app.contracts.extraction import Evidence, ExtractedValue, FieldStatus
from app.contracts.issue import DuplicateCandidate, Issue, IssueSeverity, IssueStatus
from app.contracts.record import ActionNeeded, Exclusion, Origin, StoredField, StoredRecord
from app.storage.run_store import DocumentInfo
from app.validation.duplicates import find_name_rule, read_name

CellColor = Literal["red", "yellow", "grey", "none"]

# Open issue severity → cell tint, most severe first; accepted and resolved issues do not tint
SEVERITY_COLORS: dict[IssueSeverity, CellColor] = {
    "error": "red",
    "warning": "yellow",
    "info": "grey",
}

# Issues counted in the progress ("issues resolved, 9 of 20"); grey issues never need action
PROGRESS_SEVERITIES: frozenset[IssueSeverity] = frozenset({"error", "warning"})

# Separator used to show a multi-value extraction as one text when the rule has none
DEFAULT_SEPARATOR = ", "


class SourceLocation(BaseModel):
    """Where a chunk is: document, section, page or sheet rows (resolved by code)."""

    chunk_id: str
    document_id: str | None = None
    file_name: str | None = None
    section: str | None = None
    page: int | None = None
    sheet: str | None = None
    row_range: str | None = None
    is_scanned: bool = False


class CellSource(BaseModel):
    """One evidence pair of a value: its location and the quote."""

    location: SourceLocation
    quote: str


class CellAlternative(BaseModel):
    """One alternative of a conflicting field, as written, with its sources."""

    index: int
    value: str
    sources: list[CellSource]


class IssueSummary(BaseModel):
    """An issue as the grid shows it (open or accepted).

    `note_required`: accepting it needs a note (catalogue). `sources`: the chunks the issue's
    finding cites (e.g. missed candidates, challenged excluded items), only chunks of the run.
    `duplicate_candidates`: the existing types a duplicate issue names (`details.candidates`).
    """

    issue_id: str
    code: str
    severity: IssueSeverity
    status: IssueStatus
    message: str
    individual_review: bool
    note_required: bool
    sources: list[SourceLocation]
    duplicate_candidates: list[DuplicateCandidate]


class ReviewCell(BaseModel):
    """One field of one record in the grid."""

    field: str
    column: str
    value: str | None
    display_value: str | None
    written_value: str | None
    origin: Origin
    extraction_status: FieldStatus | None
    is_placeholder: bool
    color: CellColor
    issues: list[IssueSummary]
    sources: list[CellSource]
    alternatives: list[CellAlternative]


class ReviewRow(BaseModel):
    """One record: action needed, name, where it was found, record issues and its cells."""

    record_id: str
    name: str | None
    action_needed: ActionNeeded
    found_in: list[SourceLocation]
    exclusion: Exclusion | None
    record_issues: list[IssueSummary]
    cells: list[ReviewCell]


class ReviewCounts(BaseModel):
    """Summary strip counts; issue counts leave out excluded records.

    Progress: `total_issues` counts red and yellow issues (any status) of included records and
    the run; `resolved_issues` counts those that are resolved or accepted.
    """

    records: int
    to_fix: int
    to_check: int
    excluded: int
    open_errors: int
    open_warnings: int
    resolved_issues: int
    total_issues: int


class ReviewView(BaseModel):
    """The whole review grid: rows, run-level issues and counts."""

    rows: list[ReviewRow]
    run_issues: list[IssueSummary]
    counts: ReviewCounts


def build_review_view(
    records: Sequence[StoredRecord],
    issues: Sequence[Issue],
    field_rules: FieldRules,
    chunks: Sequence[Chunk],
    documents: Sequence[DocumentInfo],
) -> ReviewView:
    """Build the flattened view of a run from its records, issues, chunks and documents."""
    locator = SourceLocator(chunks, documents)
    shown = [issue for issue in issues if issue.status != "resolved"]
    rows = [build_row(record, shown, field_rules, locator) for record in records]
    run_issues = [summarize_issue(issue, locator) for issue in shown if issue.record_id is None]
    return ReviewView(rows=rows, run_issues=run_issues, counts=count_review(records, issues))


class SourceLocator:
    """Resolves chunk IDs to locations, with the document's file name."""

    def __init__(self, chunks: Sequence[Chunk], documents: Sequence[DocumentInfo]) -> None:
        """Index the chunks and documents by ID."""
        self.chunks = {chunk.chunk_id: chunk for chunk in chunks}
        self.file_names = {document.document_id: document.file_name for document in documents}

    def locate(self, chunk_id: str) -> SourceLocation:
        """Return a chunk's location; an unknown chunk ID gives only the ID."""
        chunk = self.chunks.get(chunk_id)
        if chunk is None:
            return SourceLocation(chunk_id=chunk_id)
        return SourceLocation(
            chunk_id=chunk_id,
            document_id=chunk.document_id,
            file_name=self.file_names.get(chunk.document_id),
            section=chunk.section,
            page=chunk.page,
            sheet=chunk.sheet,
            row_range=chunk.row_range,
            is_scanned=chunk.is_scanned,
        )

    def locate_known(self, chunk_ids: Sequence[str]) -> list[SourceLocation]:
        """Return the locations of the chunk IDs that are chunks of the run (others left out)."""
        return [self.locate(chunk_id) for chunk_id in chunk_ids if chunk_id in self.chunks]

    def locate_evidence(self, evidence: Sequence[Evidence]) -> list[CellSource]:
        """Return each evidence pair with its location."""
        return [CellSource(location=self.locate(e.chunk_id), quote=e.quote) for e in evidence]


def build_row(
    record: StoredRecord, issues: Sequence[Issue], field_rules: FieldRules, locator: SourceLocator
) -> ReviewRow:
    """Build one grid row; cells follow the field rules (loader column) order."""
    own = [issue for issue in issues if issue.record_id == record.record_id]
    cells = [
        build_cell(rule, record.fields.get(rule.key), own, field_rules, locator)
        for rule in field_rules.fields
    ]
    return ReviewRow(
        record_id=record.record_id,
        name=read_name(record, find_name_rule(field_rules)),
        action_needed=record.action_needed,
        found_in=[locator.locate(chunk_id) for chunk_id in record.found_in],
        exclusion=record.exclusion,
        record_issues=[summarize_issue(issue, locator) for issue in own if issue.field is None],
        cells=cells,
    )


def build_cell(
    rule: FieldRule,
    stored: StoredField | None,
    record_issues: Sequence[Issue],
    field_rules: FieldRules,
    locator: SourceLocator,
) -> ReviewCell:
    """Build one cell: value, display value, as written, color, issues, sources, alternatives."""
    field_issues = [issue for issue in record_issues if issue.field == rule.key]
    value = stored.output.value if stored is not None else None
    extraction = stored.extraction if stored is not None else None
    is_placeholder = rule.role == "blank_for_now"
    # The placeholder is display only: the value stays empty and is exported blank
    display_value = field_rules.placeholder_value if is_placeholder else value
    written = format_written(rule, extraction.value) if extraction is not None else None
    return ReviewCell(
        field=rule.key,
        column=rule.column,
        value=value,
        display_value=display_value,
        written_value=written if written != value else None,
        origin=stored.output.origin if stored is not None else rule_origin(rule),
        extraction_status=extraction.status if extraction is not None else None,
        is_placeholder=is_placeholder,
        color="grey" if is_placeholder else pick_color(field_issues),
        issues=[summarize_issue(issue, locator) for issue in field_issues],
        sources=locator.locate_evidence(extraction.evidence) if extraction is not None else [],
        alternatives=build_alternatives(rule, stored, locator),
    )


def rule_origin(rule: FieldRule) -> Origin:
    """Return the origin of a field missing from the record (only non-extracted roles)."""
    return "extracted" if rule.role == "extracted" else rule.role


def format_written(rule: FieldRule, value: ExtractedValue | None) -> str | None:
    """Return an extracted value as one text, as written (a list joined for display)."""
    if value is None or isinstance(value, str):
        return value
    return (rule.separator or DEFAULT_SEPARATOR).join(value)


def build_alternatives(
    rule: FieldRule, stored: StoredField | None, locator: SourceLocator
) -> list[CellAlternative]:
    """Return a conflicting field's alternatives, as written, with their sources."""
    if stored is None or stored.extraction is None:
        return []
    return [
        CellAlternative(
            index=index,
            value=format_written(rule, alternative.value) or "",
            sources=locator.locate_evidence(alternative.evidence),
        )
        for index, alternative in enumerate(stored.extraction.alternatives)
    ]


def pick_color(issues: Sequence[Issue]) -> CellColor:
    """Return the tint of the most severe open issue, or none."""
    open_severities = {issue.severity for issue in issues if issue.status == "open"}
    # The colors are listed from most to least severe
    for severity, color in SEVERITY_COLORS.items():
        if severity in open_severities:
            return color
    return "none"


def summarize_issue(issue: Issue, locator: SourceLocator) -> IssueSummary:
    """Return the grid's view of an issue, with the locations of the chunks it cites."""
    return IssueSummary(
        issue_id=issue.issue_id,
        code=issue.code,
        severity=issue.severity,
        status=issue.status,
        message=issue.message,
        individual_review=issue.individual_review,
        note_required=issue.note_required,
        sources=locator.locate_known(read_source_ids(issue)),
        duplicate_candidates=read_duplicate_candidates(issue),
    )


def read_source_ids(issue: Issue) -> list[str]:
    """Return the chunk IDs in an issue's `details.sources`, or none."""
    sources = issue.details.get("sources")
    if not isinstance(sources, list):
        return []
    return [source for source in sources if isinstance(source, str)]


def read_duplicate_candidates(issue: Issue) -> list[DuplicateCandidate]:
    """Return the existing types in an issue's `details.candidates`, or none.

    An entry that does not have the candidate shape is left out, never filled in.
    """
    entries = issue.details.get("candidates")
    if not isinstance(entries, list):
        return []
    candidates: list[DuplicateCandidate] = []
    for entry in entries:
        try:
            candidates.append(DuplicateCandidate.model_validate(entry))
        except ValidationError:
            continue
    return candidates


def count_review(records: Sequence[StoredRecord], issues: Sequence[Issue]) -> ReviewCounts:
    """Count records by action needed, open red and yellow issues, and issues resolved so far."""
    excluded_ids = {record.record_id for record in records if record.exclusion is not None}
    live = [
        issue for issue in issues if issue.status == "open" and issue.record_id not in excluded_ids
    ]
    actions = [record.action_needed for record in records]
    progress = find_progress_issues(issues, excluded_ids)
    return ReviewCounts(
        records=len(records),
        to_fix=actions.count("fix"),
        to_check=actions.count("check"),
        excluded=len(excluded_ids),
        open_errors=sum(1 for issue in live if issue.severity == "error"),
        open_warnings=sum(1 for issue in live if issue.severity == "warning"),
        resolved_issues=sum(1 for issue in progress if issue.status != "open"),
        total_issues=len(progress),
    )


def find_progress_issues(issues: Sequence[Issue], excluded_ids: set[str]) -> list[Issue]:
    """Return the issues progress counts: red and yellow, of included records or the run."""
    return [
        issue
        for issue in issues
        if issue.severity in PROGRESS_SEVERITIES and issue.record_id not in excluded_ids
    ]
