"""Re-extraction problems (ARCHITECTURE §5): what verification found that re-extraction fixes.

Any field verdict, a citation `not_verified`, an unreported conflict, a `should_be_split` record
verdict, or a missed candidate. Routing uses the list to decide; the extraction node sends it.
"""

from collections.abc import Sequence

from app.contracts.record import StoredRecord
from app.contracts.verification import VerificationOutput
from app.llm.prompt_builder import ReextractionProblem

# Problem names written into the re-extraction prompt
CITATION_NOT_VERIFIED = "citation not verified (quote not in its chunk, or value not in the quote)"
UNREPORTED_CONFLICT = "unreported conflict"
MISSED_CANDIDATE = "missed candidate"

# The only record verdict re-extraction can fix
SPLIT_VERDICT = "should_be_split"


def find_reextraction_problems(
    records: Sequence[StoredRecord], findings: VerificationOutput | None
) -> list[ReextractionProblem]:
    """Return every problem re-extraction should fix, on known records and missed items."""
    problems = find_citation_problems(records)
    if findings is None:
        return problems
    known_ids = {record.record_id for record in records}
    problems += find_finding_problems(findings, known_ids)
    # Missed items are not records yet: they are named as written
    problems += [
        ReextractionProblem(
            item=missed.name_as_written,
            problem=MISSED_CANDIDATE,
            chunk_ids=missed.sources,
            note=missed.reason,
        )
        for missed in findings.missed_candidates
    ]
    return problems


def find_finding_problems(
    findings: VerificationOutput, known_ids: set[str]
) -> list[ReextractionProblem]:
    """Return the agent's field verdicts, unreported conflicts and split verdicts as problems."""
    problems: list[ReextractionProblem] = []
    # Findings on record IDs that are not in the run are ignored
    for finding in findings.field_findings:
        if finding.record_id in known_ids:
            problems.append(
                ReextractionProblem(
                    record_id=finding.record_id,
                    field=finding.field,
                    problem=finding.verdict,
                    chunk_ids=finding.sources,
                    note=finding.note,
                )
            )
    for conflict in findings.unreported_conflicts:
        if conflict.record_id in known_ids:
            problems.append(
                ReextractionProblem(
                    record_id=conflict.record_id,
                    field=conflict.field,
                    problem=UNREPORTED_CONFLICT,
                    chunk_ids=conflict.sources,
                    note=conflict.note,
                )
            )
    for record_finding in findings.record_findings:
        if record_finding.record_id in known_ids and record_finding.verdict == SPLIT_VERDICT:
            problems.append(
                ReextractionProblem(
                    record_id=record_finding.record_id,
                    problem=record_finding.verdict,
                    note=record_finding.note,
                )
            )
    return problems


def find_citation_problems(records: Sequence[StoredRecord]) -> list[ReextractionProblem]:
    """Return a problem for each field whose citation check is `not_verified`."""
    problems: list[ReextractionProblem] = []
    for record in records:
        for key, stored in record.fields.items():
            citation_check = stored.verification.citation_check if stored.verification else None
            if citation_check == "not_verified":
                problems.append(
                    ReextractionProblem(
                        record_id=record.record_id, field=key, problem=CITATION_NOT_VERIFIED
                    )
                )
    return problems


def find_affected_record_ids(problems: Sequence[ReextractionProblem]) -> set[str]:
    """Return the IDs of the records the problems name."""
    return {problem.record_id for problem in problems if problem.record_id is not None}
