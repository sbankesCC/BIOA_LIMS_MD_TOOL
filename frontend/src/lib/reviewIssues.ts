// Issue lists for the Review screen: a record's issues, the run's open issues in navigation
// order (UI_SPEC §4.3 "Issue 1 of 11 open"), row filters and the record name field.
import type { IssueSummary, ReviewCell, ReviewRow, ReviewView, RunField } from "../api/types";

/** An issue with where it sits: its record (null for a run issue) and its field (null if none). */
export interface IssueRef {
  issue: IssueSummary;
  recordId: string | null;
  field: string | null;
}

/** The grid filters of the summary strip. */
export type RowFilter = "all" | "needs_action" | "excluded";

/** Return a record's issues: record-level ones first, then each field's in column order. */
export function listRowIssues(row: ReviewRow): IssueRef[] {
  const recordLevel = row.record_issues.map((issue) => ({ issue, recordId: row.record_id, field: null }));
  const fieldLevel = row.cells.flatMap((cell) =>
    cell.issues.map((issue) => ({ issue, recordId: row.record_id, field: cell.field })),
  );
  return [...recordLevel, ...fieldLevel];
}

/** Return the run-level issues as issue references. */
export function listRunIssues(view: ReviewView): IssueRef[] {
  return view.run_issues.map((issue) => ({ issue, recordId: null, field: null }));
}

/** Return true for an issue the arrows move through: open, red or yellow (grey never blocks). */
export function isNavigable(issue: IssueSummary): boolean {
  return issue.status === "open" && issue.severity !== "info";
}

/**
 * Return every open red or yellow issue of the run in navigation order: records in grid order
 * (excluded ones left out), then run issues. Issues in `savedIds` wait for the re-check and
 * are left out.
 */
export function listOpenIssues(view: ReviewView, savedIds: ReadonlySet<string>): IssueRef[] {
  const included = view.rows.filter((row) => row.exclusion === null);
  const all = [...included.flatMap(listRowIssues), ...listRunIssues(view)];
  return all.filter((ref) => isNavigable(ref.issue) && !savedIds.has(ref.issue.issue_id));
}

/** Return the issue after (or before) the current one, wrapping around; null when none is left. */
export function findNeighbourIssue(
  view: ReviewView,
  savedIds: ReadonlySet<string>,
  currentIssueId: string | null,
  step: 1 | -1,
): IssueRef | null {
  // Order every open issue, saved ones included, so the current position is known
  const ordered = listOpenIssues(view, new Set());
  const open = ordered.filter((ref) => !savedIds.has(ref.issue.issue_id));
  if (open.length === 0) {
    return null;
  }
  const position = ordered.findIndex((ref) => ref.issue.issue_id === currentIssueId);
  if (position < 0) {
    return step === 1 ? open[0] : open[open.length - 1];
  }
  // Walk from the current position and take the first issue still open
  for (let offset = 1; offset <= ordered.length; offset += 1) {
    const index = (position + step * offset + ordered.length) % ordered.length;
    const candidate = ordered[index];
    if (!savedIds.has(candidate.issue.issue_id) && candidate.issue.issue_id !== currentIssueId) {
      return candidate;
    }
  }
  return null;
}

/** Return the issue with this ID anywhere in the view (records and run), or null. */
export function findIssueRef(view: ReviewView, issueId: string): IssueRef | null {
  const all = [...view.rows.flatMap(listRowIssues), ...listRunIssues(view)];
  return all.find((ref) => ref.issue.issue_id === issueId) ?? null;
}

/** Return the first open issue of a record (or of the run when `recordId` is null). */
export function findFirstOpenIssue(view: ReviewView, recordId: string | null): IssueRef | null {
  const refs = recordId === null ? listRunIssues(view) : listRowIssues(findRow(view, recordId) ?? emptyRow(recordId));
  return refs.find((ref) => isNavigable(ref.issue)) ?? refs.find((ref) => ref.issue.status === "open") ?? null;
}

/** Return the row of a record, or null. */
export function findRow(view: ReviewView, recordId: string): ReviewRow | null {
  return view.rows.find((row) => row.record_id === recordId) ?? null;
}

/** Return a row's cell for a field, or null. */
export function findCell(row: ReviewRow, field: string): ReviewCell | null {
  return row.cells.find((cell) => cell.field === field) ?? null;
}

/** Return a row with no issues, for a record that is no longer in the view. */
function emptyRow(recordId: string): ReviewRow {
  return { record_id: recordId, name: null, action_needed: "none", found_in: [], exclusion: null, record_issues: [], cells: [] };
}

/** Return the rows a filter shows. */
export function filterRows(rows: ReviewRow[], filter: RowFilter): ReviewRow[] {
  if (filter === "needs_action") {
    return rows.filter((row) => row.action_needed === "fix" || row.action_needed === "check");
  }
  if (filter === "excluded") {
    return rows.filter((row) => row.action_needed === "excluded");
  }
  return rows;
}

/**
 * Return the key of the field that names a record: the field whose value is the row's name
 * in every row that has one (the API gives the name but not its field). Null when unknown.
 */
export function findNameField(view: ReviewView, fields: RunField[]): string | null {
  const named = view.rows.filter((row) => row.name !== null);
  if (named.length === 0) {
    return null;
  }
  const match = fields.find((field) =>
    named.every((row) => findCell(row, field.key)?.value === row.name),
  );
  return match?.key ?? null;
}
