"""Graph nodes: each does one processing step and returns its state update.

Nodes read chunk text from the run store when they need it and never put it in the state.
They set the run status as they start, and never call each other: routing picks the next node.
The finish node writes the result to the review database; the run is then `in_review`.
"""

import time
from collections.abc import Callable, Sized
from datetime import UTC, datetime
from typing import Any, cast

from app.agents.common import AgentError
from app.agents.extraction import ExtractionTask, run_extraction
from app.agents.extraction_verification import VerificationTask, run_verification
from app.agents.matching import (
    MatchingTask,
    build_matching_groups,
    run_matching,
)
from app.agents.naming import NamingTask, build_naming_records, run_naming
from app.agents.step_support import CallBudget
from app.assembly.assemble import assemble_records
from app.contracts.chunk import Chunk
from app.contracts.extraction import ExcludedItem, ExtractionOutput
from app.contracts.issue import Issue
from app.contracts.record import StoredRecord
from app.contracts.run import RunStatus
from app.graph.context import (
    ProcessingContext,
    make_caller,
    make_judge_runner,
    make_plausibility_reviewer,
    read_image_size,
    read_model,
)
from app.graph.records import (
    apply_findings,
    apply_suggestions,
    build_first_records,
    clear_agent_findings,
    find_matching_suggestions,
    merge_reextraction,
)
from app.graph.reextraction import find_affected_record_ids, find_reextraction_problems
from app.graph.state import (
    ProcessingState,
    dump_excluded_items,
    dump_issues,
    dump_records,
    read_excluded_items,
    read_findings,
    read_issues,
    read_records,
)
from app.ingest.ingest import ingest_run
from app.llm.prompt_builder import build_reextraction_section
from app.llm.tracing import TracedCaller
from app.logging_setup import DetailValue, log_event
from app.normalization.normalize import normalize_records
from app.storage.run_store import RunFolder
from app.validation.issues import IssueDraft, make_issue
from app.validation.service import ProcessingFindings, make_validation_config, validate_run
from app.verification.citation_check import check_record_citations, index_chunks

# Run issue codes the graph raises itself (defined in the issue catalogue)
NO_READABLE_DOCUMENTS = "NO_READABLE_DOCUMENTS"
NO_RECORDS_FOUND = "NO_RECORDS_FOUND"

# Prompt templates of the LLM nodes
EXTRACTION_PROMPT = "extraction"
VERIFICATION_PROMPT = "extraction_verification"
MATCHING_PROMPT = "matching"
NAMING_PROMPT = "naming"

# Run issue codes of the steps that never fail a run
MATCHING_SKIPPED = "MATCHING_SKIPPED"
NAMING_SKIPPED = "NAMING_SKIPPED"

StateUpdate = dict[str, Any]
NodeFunction = Callable[[ProcessingState, ProcessingContext], StateUpdate]


def run_node(
    name: str,
    status: RunStatus | None,
    node: NodeFunction,
    state: ProcessingState,
    context: ProcessingContext,
) -> StateUpdate:
    """Run one node: set the run status, log its start and end with counts and duration."""
    run_id = state["run_id"]
    if status is not None:
        context.database.set_run_status(run_id, status)
    log_event("node_started", run_id=run_id, node=name)
    start = time.perf_counter()
    update = node(state, context)
    duration_ms = round((time.perf_counter() - start) * 1000)
    event = "node_failed" if update.get("failure_code") else "node_finished"
    level = "WARNING" if event == "node_failed" else "INFO"
    log_event(event, level, run_id, name, duration_ms=duration_ms, details=count_update(update))
    return update


def count_update(update: StateUpdate) -> dict[str, DetailValue]:
    """Return the sizes of the lists and maps a node wrote (counts only, never values)."""
    counts: dict[str, DetailValue] = {}
    for key, value in update.items():
        if isinstance(value, list | dict):
            counts[key] = len(cast(Sized, value))
    return counts


# ----- Ingest -----


def ingest_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Read every uploaded document into chunks; no readable document fails the run."""
    folder = context.run_store.open_run(state["run_id"])
    result = ingest_run(folder, context.bundle)
    issues = list(result.issues)
    failure_code: str | None = None
    if result.readable_document_count() == 0:
        failure_code = NO_READABLE_DOCUMENTS
        issues.append(make_run_issue(context, NO_READABLE_DOCUMENTS))
    # Only references go into the state: document and chunk IDs
    return {
        "document_ids": [document.document_id for document in result.documents],
        "chunk_ids": [chunk.chunk_id for chunk in result.chunks],
        "issues": dump_issues(issues),
        "failure_code": failure_code,
    }


# ----- Extraction -----


def extraction_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Extract the records; after verification, re-extract only the affected records and items."""
    folder = context.run_store.open_run(state["run_id"])
    records = read_records(state)
    findings = read_findings(state)
    # Findings in the state mean verification has run: this call is a re-extraction
    problems = find_reextraction_problems(records, findings) if findings is not None else []
    affected_ids = find_affected_record_ids(problems)
    task = ExtractionTask(
        run_id=state["run_id"],
        chunks=load_chunks(folder, state["chunk_ids"]),
        business_rules=context.bundle.business_rules,
        extraction_rules=context.bundle.extraction_rules,
        template=context.bundle.prompts[EXTRACTION_PROMPT],
        max_input_tokens=context.limits.max_input_tokens,
        reextraction_section=build_reextraction_section(records, problems),
        allowed_record_ids=frozenset(affected_ids),
    )
    try:
        output = run_extraction(
            make_state_caller(state, context, folder),
            task,
            lambda image_ref: read_image_size(context.run_store, image_ref),
        )
    except AgentError as error:
        return fail_update(state, context, error.code)
    if findings is None:
        return first_extraction_update(output, context)
    return reextraction_update(state, context, output, affected_ids)


def first_extraction_update(output: ExtractionOutput, context: ProcessingContext) -> StateUpdate:
    """Give the extracted records their IDs and store them with the excluded items."""
    records = build_first_records(output, context.bundle.business_rules)
    return {
        "records": dump_records(records),
        "excluded_items": dump_excluded_items(output.excluded_items),
    }


def reextraction_update(
    state: ProcessingState,
    context: ProcessingContext,
    output: ExtractionOutput,
    affected_ids: set[str],
) -> StateUpdate:
    """Merge a re-extraction: replace returned records, flag dropped ones, add new items."""
    merged = merge_reextraction(
        read_records(state), output, affected_ids, context.bundle.business_rules
    )
    # A record dropped earlier but returned now is no longer dropped
    returned_ids = affected_ids - set(merged.dropped_record_ids)
    dropped = [rid for rid in state["dropped_record_ids"] if rid not in returned_ids]
    dropped += [rid for rid in merged.dropped_record_ids if rid not in dropped]
    excluded = merge_excluded_items(read_excluded_items(state), output.excluded_items)
    return {
        "records": dump_records(merged.records),
        "excluded_items": dump_excluded_items(excluded),
        "dropped_record_ids": dropped,
        "reextract_count": state["reextract_count"] + 1,
    }


def merge_excluded_items(
    earlier: list[ExcludedItem], new: list[ExcludedItem]
) -> list[ExcludedItem]:
    """Return the earlier excluded items plus new ones not already listed by name."""
    names = {item.item for item in earlier}
    return earlier + [item for item in new if item.item not in names]


# ----- Extraction verification -----


def verification_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Check citations (code), then ask the verification agent for problems (LLM)."""
    folder = context.run_store.open_run(state["run_id"])
    chunks = load_chunks(folder, state["chunk_ids"])
    chunk_index = index_chunks(chunks)
    # Each pass starts fresh: earlier agent verdicts are replaced by this pass's findings
    records = [
        clear_agent_findings(check_record_citations(record, chunk_index))
        for record in read_records(state)
    ]
    task = VerificationTask(
        run_id=state["run_id"],
        chunks=chunks,
        records=records,
        excluded_items=read_excluded_items(state),
        business_rules=context.bundle.business_rules,
        extraction_rules=context.bundle.extraction_rules,
        template=context.bundle.prompts[VERIFICATION_PROMPT],
    )
    try:
        findings = run_verification(make_state_caller(state, context, folder), task)
    except AgentError as error:
        return fail_update(state, context, error.code)
    records = [apply_findings(record, findings) for record in records]
    return {"records": dump_records(records), "findings": findings.model_dump(mode="json")}


# ----- Normalization, Matching, Naming, Assembly and validation -----


def normalization_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Write every extracted field's normalization section (code only)."""
    business_rules = context.bundle.business_rules
    records = normalize_records(read_records(state), business_rules, context.lookup_lists)
    return {"records": dump_records(records)}


def matching_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Suggest list values for unresolved values; never fails the run (skips with a warning)."""
    business_rules = context.bundle.business_rules
    records = read_records(state)
    groups = build_matching_groups(
        records, business_rules, context.lookup_lists, context.limits.matching_shortlist_size
    )
    # Nothing unresolved: no call, no warning
    if not groups:
        return {}
    task = MatchingTask(
        run_id=state["run_id"],
        groups=groups,
        business_rules=business_rules,
        template=context.bundle.prompts[MATCHING_PROMPT],
        model=read_model(context.client, "matching"),
    )
    folder = context.run_store.open_run(state["run_id"])
    budget = CallBudget(context.limits.max_matching_calls)
    result = run_matching(
        make_state_caller(state, context, folder), task, context.step_caches.matching, budget
    )
    suggestions = find_matching_suggestions(groups, result)
    owned = {rule.key for rule in business_rules.fields if rule.matching_allowed}
    updated = apply_suggestions(records, suggestions, owned)
    update: StateUpdate = {"records": dump_records(updated)}
    if result.is_skipped:
        update["issues"] = add_run_issue(state, context, MATCHING_SKIPPED)
    return update


def naming_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Suggest a name for each included record; never fails the run (skips with a warning)."""
    business_rules = context.bundle.business_rules
    records = read_records(state)
    naming_records = build_naming_records(records, business_rules)
    if not naming_records:
        return {}
    name_key = business_rules.record_name_field().key
    task = NamingTask(
        run_id=state["run_id"],
        records=naming_records,
        business_rules=business_rules,
        template=context.bundle.prompts[NAMING_PROMPT],
        model=read_model(context.client, "naming"),
        taken_names=[
            r.fields[name_key].output.value or "" for r in records if is_name_set(r, name_key)
        ],
    )
    folder = context.run_store.open_run(state["run_id"])
    budget = CallBudget(context.limits.max_naming_calls)
    result = run_naming(
        make_state_caller(state, context, folder), task, context.step_caches.naming, budget
    )
    suggestions = {(rid, name_key): suggestion for rid, suggestion in result.suggestions.items()}
    log_dropped_names(state["run_id"], result.dropped)
    updated = apply_suggestions(records, suggestions, [name_key])
    update: StateUpdate = {"records": dump_records(updated)}
    if result.is_skipped:
        update["issues"] = add_run_issue(state, context, NAMING_SKIPPED)
    return update


def assembly_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Write every field's output section from the normalized values (code only)."""
    records = assemble_records(read_records(state), context.bundle.business_rules)
    return {"records": dump_records(records)}


def validation_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Find every issue; the run's earlier issues (ingest, graph) pass through unchanged."""
    records = read_records(state)
    previous = read_issues(state)
    if not records:
        previous.append(make_run_issue(context, NO_RECORDS_FOUND))
    folder = context.run_store.open_run(state["run_id"])
    caller = make_state_caller(state, context, folder)
    runner = make_judge_runner(context, caller, state["run_id"])
    result = validate_run(
        records,
        make_validation_config(context.bundle, context.lookup_lists),
        runner,
        context.reference,
        read_processing_findings(state),
        previous,
        make_plausibility_reviewer(context, caller, state["run_id"]),
    )
    return {"records": dump_records(result.records), "issues": dump_issues(result.issues)}


# ----- End nodes -----


def finish_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Write records, issues and findings to the review database; the run is in review."""
    run_id = state["run_id"]
    context.database.save_processing_result(
        run_id,
        read_records(state),
        read_issues(state),
        read_processing_findings(state),
        read_excluded_items(state),
        datetime.now(UTC),
    )
    context.database.set_run_status(run_id, "in_review")
    return {}


def failed_node(state: ProcessingState, context: ProcessingContext) -> StateUpdate:
    """Write the run issues (with the failure) to the review database; the run has failed."""
    run_id = state["run_id"]
    context.database.save_processing_result(
        run_id,
        [],
        read_issues(state),
        read_processing_findings(state),
        read_excluded_items(state),
        datetime.now(UTC),
    )
    context.database.set_run_status(run_id, "failed")
    return {}


# ----- Helpers -----


def load_chunks(folder: RunFolder, chunk_ids: list[str]) -> list[Chunk]:
    """Read the state's chunks from the run store, in their stored order."""
    wanted = set(chunk_ids)
    return [chunk for chunk in folder.read_chunks() if chunk.chunk_id in wanted]


def make_state_caller(
    state: ProcessingState, context: ProcessingContext, folder: RunFolder
) -> TracedCaller:
    """Return a traced LLM caller that writes the run's captured versions into each trace."""
    return make_caller(context, folder, state["config_versions"])


def read_processing_findings(state: ProcessingState) -> ProcessingFindings:
    """Return the findings validation needs: verification, dropped records, excluded items."""
    return ProcessingFindings(
        verification=read_findings(state),
        dropped_record_ids=state["dropped_record_ids"],
        excluded_items=read_excluded_items(state),
    )


def add_run_issue(state: ProcessingState, context: ProcessingContext, code: str) -> list[Any]:
    """Return the state's issues with one more run issue, as state JSON."""
    return dump_issues([*read_issues(state), make_run_issue(context, code)])


def is_name_set(record: StoredRecord, name_key: str) -> bool:
    """Return True if the record already has a name (a person set it)."""
    return bool(record.fields[name_key].output.value)


def log_dropped_names(run_id: str, dropped: dict[str, str]) -> None:
    """Log how many name suggestions failed the code checks, by reason (counts only)."""
    if not dropped:
        return
    counts: dict[str, DetailValue] = {}
    for reason in dropped.values():
        counts[reason] = int(counts.get(reason, 0)) + 1
    log_event("suggestions_dropped", level="WARNING", run_id=run_id, node="naming", details=counts)


def make_run_issue(context: ProcessingContext, code: str) -> Issue:
    """Build a run issue the graph raises, from the catalogue."""
    bundle = context.bundle
    return make_issue(IssueDraft(code=code), bundle.issue_catalogue, bundle.business_rules)


def fail_update(state: ProcessingState, context: ProcessingContext, code: str) -> StateUpdate:
    """Return the update that fails the run with a run issue."""
    issues = [*read_issues(state), make_run_issue(context, code)]
    return {"issues": dump_issues(issues), "failure_code": code}
