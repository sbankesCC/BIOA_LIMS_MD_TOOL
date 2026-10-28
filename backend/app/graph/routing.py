"""Routing rules (ARCHITECTURE §5): every edge of the processing graph, and only here.

Routing is code, never an LLM. Nodes never call each other: they set state, and these rules pick
the next node. Each conditional decision is logged with counts (no values).
"""

from collections.abc import Callable

from langgraph.graph import END, START  # pyright: ignore[reportMissingTypeStubs]

from app.graph.reextraction import find_reextraction_problems
from app.graph.state import ProcessingState, read_findings, read_records
from app.logging_setup import log_event

# Node names
INGEST = "ingest"
EXTRACTION = "extraction"
VERIFICATION = "extraction_verification"
TRANSFORMATION = "transformation"
VALIDATION = "validation"
FINISH = "finish"
FAILED = "failed"

# Edges that are always taken
FIXED_EDGES: list[tuple[str, str]] = [
    (START, INGEST),
    (TRANSFORMATION, VALIDATION),
    (VALIDATION, FINISH),
    (FINISH, END),
    (FAILED, END),
]


def route_after_ingest(state: ProcessingState) -> str:
    """No readable document: failed. Otherwise extraction."""
    destination = FAILED if state["failure_code"] else EXTRACTION
    log_route(state, INGEST, destination, {"documents": len(state["document_ids"])})
    return destination


def route_after_extraction(state: ProcessingState) -> str:
    """Unparseable or too large after the retries: failed. Otherwise extraction verification."""
    destination = FAILED if state["failure_code"] else VERIFICATION
    log_route(state, EXTRACTION, destination, {"records": len(state["records"])})
    return destination


def route_after_verification(state: ProcessingState) -> str:
    """Problems found and attempts left: re-extract. Failed call: failed. Else transformation."""
    if state["failure_code"]:
        log_route(state, VERIFICATION, FAILED, {})
        return FAILED
    problems = find_reextraction_problems(read_records(state), read_findings(state))
    has_attempts_left = state["reextract_count"] < state["max_reextract"]
    # Unresolved problems are carried on as findings and become issues in validation
    destination = EXTRACTION if problems and has_attempts_left else TRANSFORMATION
    details = {"problems": len(problems), "reextract_count": state["reextract_count"]}
    log_route(state, VERIFICATION, destination, details)
    return destination


# Conditional edges: source node, its rule, and the nodes the rule may choose
CONDITIONAL_EDGES: list[tuple[str, Callable[[ProcessingState], str], list[str]]] = [
    (INGEST, route_after_ingest, [EXTRACTION, FAILED]),
    (EXTRACTION, route_after_extraction, [VERIFICATION, FAILED]),
    (VERIFICATION, route_after_verification, [EXTRACTION, TRANSFORMATION, FAILED]),
]


def log_route(
    state: ProcessingState, source: str, destination: str, counts: dict[str, int]
) -> None:
    """Log a routing decision; the destination is a `to_<node>` flag, the rest are counts."""
    details: dict[str, int | float] = {f"to_{destination}": 1, **counts}
    log_event("route_decided", run_id=state["run_id"], node=source, details=details)
