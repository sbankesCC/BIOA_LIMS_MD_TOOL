"""Graph tests with the fake LLM: synthetic documents in, a run in review (or failed) out.

They prove the plumbing (routing, re-extraction, failures, state and logs), not extraction quality.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.bundle import ConfigBundle
from app.contracts.issue import Issue
from app.contracts.log_line import LogLine
from app.contracts.reference import ReferenceData, ReferenceType
from app.graph.build import make_run_info, open_checkpointer, run_processing
from app.graph.context import ProcessingContext, ProcessingLimits
from app.llm.client import ImagePart, TextPart
from app.llm.fake_client import FakeLLMClient, FakeReply
from app.llm.tracing import read_traces
from app.logging_setup import LOGGER_NAME
from app.storage.review_db import ReviewDatabase
from app.storage.run_store import RunStore
from app.validation.judge_cache import InMemoryJudgeCache
from tests.fixtures.fake_llm import (
    TABLE_CHUNK_ID,
    empty_extraction_reply,
    extraction_reply,
    missed_row,
    unsupported_name,
    verification_reply,
)
from tests.fixtures.make_documents import (
    BROKEN_FILE,
    REAGENT_TABLE,
    SCANNED_PDF_FILE,
    WORD_FILE,
)

RUN_ID = "run_0001"
USER = "synthetic user"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

# Replies for two records (table rows 1 and 2) and a verification with nothing to report
TWO_ROWS = (("R1", 1), ("R2", 2))


@dataclass
class GraphRun:
    """A processed synthetic run: its stores and the fake client that answered."""

    database: ReviewDatabase
    run_store: RunStore
    client: FakeLLMClient
    checkpoint_path: Path

    def issue_codes(self) -> list[str]:
        """Return the codes of the run's open issues."""
        return [issue.code for issue in self.database.read_issues(RUN_ID) if issue.status == "open"]

    def issues_with_code(self, code: str) -> list[Issue]:
        """Return the run's issues with one code."""
        return [issue for issue in self.database.read_issues(RUN_ID) if issue.code == code]


def process_run(
    tmp_path: Path,
    bundle: ConfigBundle,
    documents: Mapping[str, Path],
    replies: Mapping[str, Sequence[FakeReply]],
    file_names: Sequence[str] = (WORD_FILE,),
    max_reextract: int = 1,
    max_input_tokens: int | None = None,
    reference: ReferenceData | None = None,
) -> GraphRun:
    """Store a run with the given synthetic files and process it with the fake LLM."""
    database = ReviewDatabase(tmp_path / "review.sqlite")
    run_store = RunStore(tmp_path / "storage")
    client = FakeLLMClient(replies)
    run = make_run_info(
        RUN_ID, "synthetic run", USER, NOW, bundle, bundle.lookup_lists, reference, client
    )
    database.add_run(run)
    folder = run_store.create_run(RUN_ID)
    for name in file_names:
        folder.save_upload(name, documents[name].read_bytes())
    context = ProcessingContext(
        bundle=bundle,
        lookup_lists=bundle.lookup_lists,
        reference=reference,
        client=client,
        run_store=run_store,
        database=database,
        judge_cache=InMemoryJudgeCache(),
        limits=ProcessingLimits(
            llm_retries=1, max_reextract=max_reextract, max_input_tokens=max_input_tokens
        ),
    )
    checkpoint_path = tmp_path / "checkpoints.sqlite"
    run_processing(context, RUN_ID, checkpoint_path)
    return GraphRun(database, run_store, client, checkpoint_path)


def happy_replies(bundle: ConfigBundle) -> dict[str, list[FakeReply]]:
    """Return replies for a clean run: two records, nothing to report."""
    return {
        "extraction": [extraction_reply(bundle.field_rules, TWO_ROWS)],
        "extraction_verification": [verification_reply()],
    }


def test_happy_path_ends_in_review(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Synthetic documents are ingested, extracted, verified, transformed and validated."""
    run = process_run(
        tmp_path,
        bundle,
        synthetic_documents,
        happy_replies(bundle),
        file_names=(WORD_FILE, SCANNED_PDF_FILE),
    )
    stored = run.database.read_run(RUN_ID)
    assert stored.status == "in_review"
    assert stored.models == {
        "extraction": "fake-model",
        "extraction_verification": "fake-model",
        "duplicate_judge": "fake-model",
    }
    records = run.database.read_records(RUN_ID)
    assert [record.record_id for record in records] == ["rec_0001", "rec_0002"]
    # The name is copied from the synthetic table, transformed into the output section
    name_key = bundle.field_rules.record_name_field().key
    assert records[0].fields[name_key].output.value == REAGENT_TABLE[1][0]
    verification = records[0].fields[name_key].verification
    assert verification is not None
    assert verification.citation_check == "verified"
    # Ingest and validation run issues reach the review database
    assert "SCANNED_PAGES" in run.issue_codes()
    assert "REFERENCE_DATA_MISSING" in run.issue_codes()


def test_happy_path_sends_page_images_and_traces_every_call(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """The scanned page goes to the LLM as an image part; each call has a trace."""
    run = process_run(
        tmp_path,
        bundle,
        synthetic_documents,
        happy_replies(bundle),
        file_names=(WORD_FILE, SCANNED_PDF_FILE),
    )
    request = run.client.calls_for("extraction")[0]
    images = [part for part in request.parts if isinstance(part, ImagePart)]
    assert [image.chunk_id for image in images] == ["doc02-p01-c001"]
    traces = read_traces(run.run_store.open_run(RUN_ID))
    assert [(trace.node, trace.status) for trace in traces] == [
        ("extraction", "ok"),
        ("extraction_verification", "ok"),
    ]


def test_problems_found_trigger_one_reextraction(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A missed candidate is re-extracted: existing IDs are kept and the new item gets one."""
    replies: dict[str, list[FakeReply]] = {
        "extraction": [
            extraction_reply(bundle.field_rules, TWO_ROWS),
            extraction_reply(bundle.field_rules, [("R1", 3)]),
        ],
        "extraction_verification": [
            verification_reply(missed=[missed_row(3)]),
            verification_reply(),
        ],
    }
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    records = run.database.read_records(RUN_ID)
    assert [record.record_id for record in records] == ["rec_0001", "rec_0002", "rec_0003"]
    assert [record.verification.re_extracted for record in records] == [False, False, True]
    # The re-extraction prompt lists the problem and the item as written
    second = run.client.calls_for("extraction")[1]
    prompt = "".join(part.text for part in second.parts if isinstance(part, TextPart))
    assert "# Problems to fix" in prompt
    assert REAGENT_TABLE[3][0] in prompt
    assert run.database.read_run(RUN_ID).status == "in_review"


def test_reextraction_stops_at_the_limit(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Problems that stay after MAX_REEXTRACT attempts become issues; the run goes to review."""
    replies: dict[str, list[FakeReply]] = {
        "extraction": [
            extraction_reply(bundle.field_rules, TWO_ROWS),
            empty_extraction_reply(),
        ],
        "extraction_verification": [verification_reply(missed=[missed_row(3)])],
    }
    run = process_run(tmp_path, bundle, synthetic_documents, replies, max_reextract=1)
    assert len(run.client.calls_for("extraction")) == 2
    assert len(run.client.calls_for("extraction_verification")) == 2
    assert "MISSED_CANDIDATES_UNRESOLVED" in run.issue_codes()
    assert run.database.read_run(RUN_ID).status == "in_review"


def test_no_reextraction_when_the_limit_is_zero(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """With MAX_REEXTRACT=0 problems go straight to validation as issues."""
    replies: dict[str, list[FakeReply]] = {
        "extraction": [extraction_reply(bundle.field_rules, TWO_ROWS)],
        "extraction_verification": [verification_reply(missed=[missed_row(3)])],
    }
    run = process_run(tmp_path, bundle, synthetic_documents, replies, max_reextract=0)
    assert len(run.client.calls_for("extraction")) == 1
    assert "MISSED_CANDIDATES_UNRESOLVED" in run.issue_codes()


def test_dropped_record_is_kept_and_flagged(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """An affected record the re-extraction does not return is kept, with an issue."""
    finding = unsupported_name(bundle.field_rules, "rec_0002")
    replies: dict[str, list[FakeReply]] = {
        "extraction": [extraction_reply(bundle.field_rules, TWO_ROWS), empty_extraction_reply()],
        "extraction_verification": [verification_reply(field_findings=[finding])],
    }
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    records = run.database.read_records(RUN_ID)
    assert [record.record_id for record in records] == ["rec_0001", "rec_0002"]
    dropped = run.issues_with_code("RECORD_DROPPED_ON_REEXTRACTION")
    assert [issue.record_id for issue in dropped] == ["rec_0002"]
    assert run.database.read_findings(RUN_ID).dropped_record_ids == ["rec_0002"]


def test_schema_violation_is_retried_then_fails_the_run(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Two responses that break the schema fail the run with EXTRACTION_FAILED."""
    replies: dict[str, list[FakeReply]] = {"extraction": ["synthetic: not JSON", "{}"]}
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    assert run.database.read_run(RUN_ID).status == "failed"
    assert "EXTRACTION_FAILED" in run.issue_codes()
    traces = read_traces(run.run_store.open_run(RUN_ID))
    assert [(trace.attempt, trace.status) for trace in traces] == [
        (1, "schema_violation"),
        (2, "schema_violation"),
    ]
    # The retry tells the model what was wrong
    retry_text = run.client.calls_for("extraction")[1].parts[-1]
    assert isinstance(retry_text, TextPart)
    assert "Problems in your previous response" in retry_text.text


def test_status_rule_violation_is_retried_then_succeeds(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A response citing an unknown chunk is retried; a good second response continues."""
    bad = extraction_reply(bundle.field_rules, TWO_ROWS).replace(TABLE_CHUNK_ID, "doc09-c999")
    replies: dict[str, list[FakeReply]] = {
        "extraction": [bad, extraction_reply(bundle.field_rules, TWO_ROWS)],
        "extraction_verification": [verification_reply()],
    }
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    assert run.database.read_run(RUN_ID).status == "in_review"
    assert len(run.database.read_records(RUN_ID)) == 2


def test_document_set_too_large_fails_without_a_call(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Over MAX_INPUT_TOKENS the run fails with DOCUMENT_SET_TOO_LARGE and the LLM is not called."""
    run = process_run(
        tmp_path, bundle, synthetic_documents, happy_replies(bundle), max_input_tokens=10
    )
    assert run.client.requests == []
    assert run.database.read_run(RUN_ID).status == "failed"
    assert "DOCUMENT_SET_TOO_LARGE" in run.issue_codes()


def test_no_readable_document_fails_the_run(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """Only an unreadable file: the run fails with NO_READABLE_DOCUMENTS and no LLM call."""
    run = process_run(
        tmp_path, bundle, synthetic_documents, happy_replies(bundle), file_names=(BROKEN_FILE,)
    )
    assert run.client.requests == []
    assert run.database.read_run(RUN_ID).status == "failed"
    assert {"FILE_UNREADABLE", "NO_READABLE_DOCUMENTS"} <= set(run.issue_codes())


def test_no_records_found_gives_a_run_warning(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """An extraction with no records still reaches review, with NO_RECORDS_FOUND."""
    replies: dict[str, list[FakeReply]] = {
        "extraction": [empty_extraction_reply()],
        "extraction_verification": [verification_reply()],
    }
    run = process_run(tmp_path, bundle, synthetic_documents, replies)
    assert run.database.read_run(RUN_ID).status == "in_review"
    assert "NO_RECORDS_FOUND" in run.issue_codes()


def test_duplicate_judge_is_called_for_a_similar_existing_type(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """A similar existing name is sent to the judge; "same" gives POSSIBLE_DUPLICATE."""
    existing = ReferenceType(candidate_id="ref_0001", name="Synthetic Buffer A2", version="1")
    reference = ReferenceData(version="ref-synthetic-1", types=[existing])
    judge_reply = json.dumps(
        {"judgments": [{"candidate_id": "ref_0001", "verdict": "same", "reason": "synthetic"}]}
    )
    replies = {**happy_replies(bundle), "duplicate_judge": [judge_reply]}
    run = process_run(
        tmp_path,
        bundle,
        synthetic_documents,
        replies,
        reference=reference,
    )
    judged = run.client.calls_for("duplicate_judge")
    assert len(judged) == 2
    assert {issue.record_id for issue in run.issues_with_code("POSSIBLE_DUPLICATE")} >= {"rec_0001"}


def test_state_never_contains_chunk_text(
    tmp_path: Path, bundle: ConfigBundle, synthetic_documents: dict[str, Path]
) -> None:
    """No checkpoint of the run holds a chunk's text or image data, only references."""
    run = process_run(
        tmp_path,
        bundle,
        synthetic_documents,
        happy_replies(bundle),
        file_names=(WORD_FILE, SCANNED_PDF_FILE),
    )
    chunks = run.run_store.open_run(RUN_ID).read_chunks()
    texts = [chunk.text for chunk in chunks if chunk.text]
    with open_checkpointer(run.checkpoint_path) as checkpointer:
        checkpoints = list(checkpointer.list({"configurable": {"thread_id": RUN_ID}}))
    assert checkpoints
    for checkpoint in checkpoints:
        saved = json.dumps(checkpoint.checkpoint["channel_values"], default=str)
        assert all(text not in saved for text in texts)
        assert "chunk_ids" in saved
        assert "base64" not in saved


def test_logs_hold_no_values(
    tmp_path: Path,
    bundle: ConfigBundle,
    synthetic_documents: dict[str, Path],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every log line is a contract log line; no document text or field value appears."""
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        process_run(tmp_path, bundle, synthetic_documents, happy_replies(bundle))
    lines = [record.getMessage() for record in caplog.records if record.name == LOGGER_NAME]
    assert any('"route_decided"' in line for line in lines)
    for line in lines:
        LogLine.model_validate_json(line)
        assert all(cell not in line for row in REAGENT_TABLE for cell in row)
        assert "synthetic" not in line.lower()
