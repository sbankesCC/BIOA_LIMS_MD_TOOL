"""Review view tests: placeholder cells, colors, value as written, sources, alternatives, counts.

Field keys and the placeholder are read from the client config, never written here.
"""

from app.config.bundle import ConfigBundle
from app.contracts.chunk import Chunk
from app.contracts.extraction import Alternative, Evidence, ExtractedField
from app.contracts.record import Exclusion, StoredRecord
from app.review.view import ReviewRow, build_review_view
from app.storage.run_store import DocumentInfo
from app.validation import codes
from tests.unit.review_helpers import NOW, USER
from tests.unit.validation_helpers import (
    find_rule,
    make_record,
    run_validation,
    set_output,
    update_field,
)

CHUNK = Chunk(
    chunk_id="doc01-p02-c001",
    document_id="doc01",
    page=2,
    section=None,
    sheet=None,
    row_range=None,
    kind="paragraph",
    is_scanned=False,
    text="synthetic text",
    image_ref=None,
)
DOCUMENT = DocumentInfo(
    document_id="doc01",
    file_name="synthetic method.pdf",
    file_type="pdf",
    upload_ref="runs/run_0001/uploads/doc01/synthetic method.pdf",
    sha256="0" * 64,
    size_bytes=1,
)


def build_rows(bundle: ConfigBundle, records: list[StoredRecord]) -> list[ReviewRow]:
    """Validate the records with the real config and build the view's rows."""
    result = run_validation(bundle, records)
    view = build_review_view(result.records, result.issues, bundle.field_rules, [CHUNK], [DOCUMENT])
    return view.rows


def test_blank_for_now_cells_show_the_placeholder(bundle: ConfigBundle) -> None:
    """blank_for_now fields show the config placeholder but keep an empty value."""
    row = build_rows(bundle, [make_record(bundle)])[0]
    roles = {rule.key: rule.role for rule in bundle.field_rules.fields}
    for cell in row.cells:
        if roles[cell.field] == "blank_for_now":
            assert (cell.value, cell.display_value, cell.is_placeholder) == (
                None,
                bundle.field_rules.placeholder_value,
                True,
            )
        else:
            assert not cell.is_placeholder
            assert cell.display_value == cell.value


def test_cells_are_in_loader_order_with_column_names(bundle: ConfigBundle) -> None:
    """Every loader field has a cell, in field-rules order, with its DFD column name."""
    row = build_rows(bundle, [make_record(bundle)])[0]
    assert [cell.column for cell in row.cells] == bundle.field_rules.columns()


def test_cell_color_follows_its_open_issue(bundle: ConfigBundle) -> None:
    """A red issue tints its cell red; a cell without issues has no tint."""
    row = build_rows(bundle, [make_record(bundle)])[0]
    colors = {cell.field: cell.color for cell in row.cells}
    too_long = [cell for cell in row.cells if any(i.code == codes.TOO_LONG for i in cell.issues)]
    assert [cell.color for cell in too_long] == ["red"]
    name_key = bundle.field_rules.fields[0].key
    assert colors[name_key] == "none"
    assert row.action_needed == "fix"


def test_value_as_written_is_shown_when_it_differs(bundle: ConfigBundle) -> None:
    """The extracted text appears next to the exported value only when they differ."""
    rule = find_rule(bundle.field_rules, lambda r: r.type == "decimal")
    record = make_record(bundle)
    stored = record.fields[rule.key]
    extraction = ExtractedField(
        status="found",
        value="1e4 synthetic",
        evidence=[Evidence(chunk_id=CHUNK.chunk_id, quote="1e4 synthetic")],
    )
    record = update_field(record, rule.key, stored.model_copy(update={"extraction": extraction}))
    record = set_output(record, rule.key, "10000")
    cells = {cell.field: cell for cell in build_rows(bundle, [record])[0].cells}
    assert (cells[rule.key].value, cells[rule.key].written_value) == ("10000", "1e4 synthetic")
    assert cells[rule.key].sources[0].location.file_name == DOCUMENT.file_name
    assert cells[rule.key].sources[0].location.page == 2
    name_key = bundle.field_rules.fields[0].key
    assert cells[name_key].written_value is None


def test_found_in_and_alternatives_are_resolved(bundle: ConfigBundle) -> None:
    """Found in gives document and page; a conflict lists its alternatives with sources."""
    rule = find_rule(bundle.field_rules, lambda r: r.type == "text" and r.lookup_sheet is None)
    alternatives = [
        Alternative(value=v, evidence=[Evidence(chunk_id=CHUNK.chunk_id, quote=v)])
        for v in ("synthetic one", "synthetic two")
    ]
    record = make_record(bundle).model_copy(update={"found_in": [CHUNK.chunk_id, "doc09-c001"]})
    stored = record.fields[rule.key].model_copy(
        update={
            "extraction": ExtractedField(
                status="conflicting", alternatives=alternatives, warning="x"
            )
        }
    )
    row = build_rows(bundle, [update_field(record, rule.key, stored)])[0]
    assert [(loc.file_name, loc.page) for loc in row.found_in] == [
        (DOCUMENT.file_name, 2),
        (None, None),
    ]
    cell = next(cell for cell in row.cells if cell.field == rule.key)
    assert [(alt.index, alt.value) for alt in cell.alternatives] == [
        (0, "synthetic one"),
        (1, "synthetic two"),
    ]


def test_counts_leave_out_excluded_records(bundle: ConfigBundle) -> None:
    """Counts give records by action needed; issue counts skip excluded records."""
    excluded = make_record(bundle, "rec_0002", "Syn B").model_copy(
        update={"exclusion": Exclusion(by=USER, at=NOW, reason="synthetic")}
    )
    result = run_validation(bundle, [make_record(bundle), excluded])
    view = build_review_view(result.records, result.issues, bundle.field_rules, [], [])
    counts = view.counts
    assert (counts.records, counts.to_fix, counts.excluded) == (2, 1, 1)
    assert counts.open_errors == 1
    assert view.rows[1].exclusion is not None
