"""M7 tests: re-check runs Assembly and the plausibility reviewer; export and audit additions.

Field keys, lookup values and table cells are read from the client config, never written here.
"""

from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.agents.plausibility import PlausibilityResult
from app.assembly.derivations import find_table, find_target
from app.config.bundle import ConfigBundle
from app.config.business_rules import FieldDefinition
from app.contracts.chunk import Chunk
from app.contracts.plausibility import PlausibilityFinding, PlausibilityRecord
from app.contracts.record import Suggestion
from app.export.service import ExportContext, export_run
from app.review.service import ReviewContext
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunFolder, RunStore
from app.validation import codes
from app.validation.service import make_validation_config
from tests.unit.review_helpers import (
    NOW,
    RUN_ID,
    USER,
    find_issues,
    make_context,
    read_record,
    recheck,
    save,
    set_value,
    start_review,
    use_suggestion,
)
from tests.unit.validation_helpers import find_rule, make_record, set_output, update_field


class CountingReviewer:
    """A plausibility reviewer that records what it was asked and returns set findings."""

    def __init__(self, findings: list[PlausibilityFinding] | None = None) -> None:
        """Keep the findings to return for every review."""
        self.findings = findings or []
        self.reviewed: list[list[PlausibilityRecord]] = []

    def review(self, records: list[PlausibilityRecord]) -> PlausibilityResult:
        """Remember the records and return the findings."""
        self.reviewed.append(records)
        return PlausibilityResult(findings=self.findings)


@pytest.fixture
def context(bundle: ConfigBundle) -> ReviewContext:
    """Return a review context on the run config."""
    return make_context(make_validation_config(bundle))


def vendor_rule(bundle: ConfigBundle) -> FieldDefinition:
    """Return the extracted lookup field that the Consumable Class derivation reads."""
    table = find_table(bundle.business_rules, "Class table")
    assert table is not None
    return next(r for r in bundle.business_rules.fields if r.column == table.columns[0])


def class_rule(bundle: ConfigBundle) -> FieldDefinition:
    """Return the derived field the Class table fills."""
    table = find_table(bundle.business_rules, "Class table")
    assert table is not None
    return find_target(bundle.business_rules, table)


def bal_name(bundle: ConfigBundle) -> str:
    """Return a vendor name the Class table counts as one of BAL's (from the config)."""
    table = find_table(bundle.business_rules, "BAL vendor names")
    assert table is not None
    return table.active_rows()[0][table.columns[0]]


# ----- Re-check runs Assembly -----


def test_recheck_rederives_after_the_vendor_is_changed(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A person's change to the vendor changes the derived class on the next re-check."""
    vendor, derived = vendor_rule(bundle), class_rule(bundle)
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    before = read_record(database).fields[derived.key].output
    assert before.origin == "derived"
    save(database, context, set_value("chg_0001", vendor.key, bal_name(bundle), reason="synthetic"))
    recheck(database, context)
    after = read_record(database).fields[derived.key].output
    assert after.origin == "derived"
    assert after.value != before.value


def test_recheck_keeps_a_derived_value_a_person_set(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A derived field a person set is not recomputed, and the mismatch is flagged."""
    vendor, derived = vendor_rule(bundle), class_rule(bundle)
    values = bundle.lookup_lists.sheets[derived.lookup_sheet or ""]
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    typed = next(v for v in values if v != read_record(database).fields[derived.key].output.value)
    save(database, context, set_value("chg_0001", derived.key, typed, reason="synthetic"))
    save(database, context, set_value("chg_0002", vendor.key, bal_name(bundle), reason="synthetic"))
    recheck(database, context)
    output = read_record(database).fields[derived.key].output
    assert (output.value, output.origin) == (typed, "user_edited")
    mismatches = find_issues(database, codes.DERIVED_VALUE_MISMATCH, "open")
    assert [issue.field for issue in mismatches] == [derived.key]


# ----- Re-check runs the plausibility reviewer -----


def test_recheck_runs_the_reviewer_again_after_an_edit(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """The reviewer is called on every re-check, with the values after the edit."""
    reviewer = CountingReviewer()
    context = replace(context, plausibility=reviewer)
    vendor = vendor_rule(bundle)
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    save(database, context, set_value("chg_0001", vendor.key, bal_name(bundle), reason="synthetic"))
    recheck(database, context)
    assert len(reviewer.reviewed) == 1
    [review_record] = reviewer.reviewed[0]
    assert review_record.values[vendor.key] == bal_name(bundle)


def test_plausibility_finding_survives_and_clears_with_the_reviewer(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A finding is kept while the reviewer repeats it, and resolved when it stops."""
    name_key = bundle.business_rules.record_name_field().key
    finding = PlausibilityFinding(
        record_id="rec_0001", check_id="SYN-PL", fields=[name_key], reason="synthetic"
    )
    reviewer = CountingReviewer([finding])
    context = replace(context, plausibility=reviewer)
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    recheck(database, context)
    assert len(find_issues(database, codes.PLAUSIBILITY_CHECK, "open")) == 1
    reviewer.findings = []
    recheck(database, context)
    assert find_issues(database, codes.PLAUSIBILITY_CHECK, "open") == []
    assert len(find_issues(database, codes.PLAUSIBILITY_CHECK, "resolved")) == 1


def test_without_a_reviewer_plausibility_issues_are_kept(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """A context with no reviewer leaves the plausibility issues already found as they are."""
    name_key = bundle.business_rules.record_name_field().key
    finding = PlausibilityFinding(
        record_id="rec_0001", check_id="SYN-PL", fields=[name_key], reason="synthetic"
    )
    with_reviewer = replace(context, plausibility=CountingReviewer([finding]))
    database = start_review(tmp_path, bundle, with_reviewer, [make_record(bundle)])
    recheck(database, with_reviewer)
    recheck(database, context)
    assert len(find_issues(database, codes.PLAUSIBILITY_CHECK, "open")) == 1


# ----- Why no suggestion -----


def test_name_not_set_shows_why_no_name_was_suggested(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext
) -> None:
    """The reason stored with the field is carried in the NAME_NOT_SET issue's details."""
    key = bundle.business_rules.record_name_field().key
    record = set_output(make_record(bundle), key, None)
    stored = record.fields[key].model_copy(
        update={"no_suggestion_reason": "The suggested name was longer than the limit."}
    )
    database = start_review(tmp_path, bundle, context, [update_field(record, key, stored)])
    [issue] = find_issues(database, codes.NAME_NOT_SET, "open")
    assert issue.details == {
        "no_suggestion_reason": "The suggested name was longer than the limit."
    }


# ----- Export and audit -----


@pytest.fixture
def run_folder(tmp_path: Path) -> RunFolder:
    """Create the run's folder with one synthetic document and one chunk."""
    folder = RunStore(tmp_path / "storage").create_run(RUN_ID)
    folder.save_upload("synthetic method.docx", b"synthetic document")
    chunk = Chunk(
        chunk_id="doc01-c001",
        document_id="doc01",
        page=None,
        section="Synthetic section",
        sheet=None,
        row_range=None,
        kind="paragraph",
        is_scanned=False,
        text="synthetic quote",
        image_ref=None,
    )
    folder.write_chunks([chunk])
    return folder


def export_files(
    database: ReviewDatabase, bundle: ConfigBundle, context: ReviewContext, folder: RunFolder
) -> tuple[Path, Path]:
    """Export the run and return the loader and audit file paths."""
    export_context = ExportContext(
        review=context, template=bundle.export_template, models={"extraction": "synthetic-model"}
    )
    info = export_run(database, export_context, folder, RUN_ID, USER, NOW)
    return folder.resolve_ref(info.loader_file), folder.resolve_ref(info.audit_file)


def test_export_round_trip_has_every_column_derived_values_and_blank_expiry(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext, run_folder: RunFolder
) -> None:
    """The loader has all template columns; derived fields hold their values; unfilled are blank."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    loader, _ = export_files(database, bundle, context, run_folder)
    sheet = load_workbook(loader)[bundle.export_template.sheet.name]
    rows = list(sheet.iter_rows(values_only=True))
    headers = bundle.export_template.headers
    assert list(rows[0]) == headers
    assert len(headers) == len(bundle.business_rules.fields)
    record = read_record(database)
    for rule in bundle.business_rules.fields:
        value = rows[1][headers.index(rule.column)]
        if rule.role in ("system", "blank_for_now"):
            assert value is None
        elif rule.role == "derived":
            assert value == record.fields[rule.key].output.value
    derived_values = [
        rows[1][headers.index(r.column)] for r in bundle.business_rules.derived_fields()
    ]
    assert any(value is not None for value in derived_values)


def test_used_suggestion_is_audited(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext, run_folder: RunFolder
) -> None:
    """A suggestion a person used shows in Values (How set, Suggestion) and in Suggestions used."""
    rule = find_rule(
        bundle.business_rules,
        lambda r: r.lookup_sheet is not None and r.requirement == "optional",
    )
    assert rule.lookup_sheet is not None
    chosen = bundle.lookup_lists.sheets[rule.lookup_sheet][0]
    record = set_output(make_record(bundle), rule.key, None)
    suggestion = Suggestion(value=chosen, source="matching", reason="synthetic reason")
    stored = record.fields[rule.key].model_copy(update={"suggestion": suggestion})
    database = start_review(tmp_path, bundle, context, [update_field(record, rule.key, stored)])
    save(database, context, use_suggestion("chg_0001", rule.key))
    _, audit = export_files(database, bundle, context, run_folder)
    workbook = load_workbook(audit)
    values = list(workbook["Values"].iter_rows(values_only=True))
    row = next(r for r in values[1:] if r[2] == rule.column)
    assert (row[4], row[5], row[6], row[7]) == (
        chosen,
        "from suggestion",
        chosen,
        "synthetic reason",
    )
    used = list(workbook["Suggestions used"].iter_rows(values_only=True))
    # The value as written is what the document gave, not the value chosen
    written = stored.extraction.value if stored.extraction else None
    assert used[1] == ("rec_0001", rule.column, written, chosen)


def test_audit_context_sheet_lists_the_found_context_values(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext, run_folder: RunFolder
) -> None:
    """The Context sheet has one row per record and context attribute."""
    database = start_review(tmp_path, bundle, context, [make_record(bundle)])
    _, audit = export_files(database, bundle, context, run_folder)
    rows = list(load_workbook(audit)["Context"].iter_rows(values_only=True))
    attributes = [a.key for a in bundle.business_rules.context_fields()]
    assert [(row[0], row[1]) for row in rows[1:]] == [("rec_0001", key) for key in attributes]
    assert all(row[2] == "synthetic" for row in rows[1:])


def test_normalized_values_are_marked_normalized(
    tmp_path: Path, bundle: ConfigBundle, context: ReviewContext, run_folder: RunFolder
) -> None:
    """An extracted value Normalization changed is "normalized" in How set."""
    rule = find_rule(
        bundle.business_rules,
        lambda r: r.type == "text" and r.lookup_sheet is None and not r.is_record_name,
    )
    record = make_record(bundle)
    stored = record.fields[rule.key]
    # Written with extra spaces; normalized to the plain text that is exported
    extraction = (
        stored.extraction.model_copy(update={"value": "  synthetic  "})
        if stored.extraction
        else None
    )
    record = update_field(record, rule.key, stored.model_copy(update={"extraction": extraction}))
    database = start_review(tmp_path, bundle, context, [record])
    _, audit = export_files(database, bundle, context, run_folder)
    values = list(load_workbook(audit)["Values"].iter_rows(values_only=True))
    row = next(r for r in values[1:] if r[2] == rule.column)
    assert row[5] == "normalized"
