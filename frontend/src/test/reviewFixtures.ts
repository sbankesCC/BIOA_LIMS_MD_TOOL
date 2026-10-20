// Synthetic Review screen data for tests (labeled synthetic: no BioA fields or values), and a
// mocked fetch that records each request's method, path and JSON body.
import { vi } from "vitest";
import type { IssueSummary, ReviewCell, ReviewRow, ReviewView, RunField, RunFieldList } from "../api/types";
import { makeRunDetail } from "./helpers";

/** Return a synthetic field, changed by `overrides`. */
export function makeField(overrides: Partial<RunField> = {}): RunField {
  return {
    key: "synthetic_field",
    column: "Synthetic Field",
    role: "extracted",
    requirement: "optional",
    type: "text",
    max_length: 40,
    has_lookup_list: false,
    is_boolean: false,
    multi_value: false,
    separator: null,
    allowed_values: [],
    is_record_name: false,
    ...overrides,
  };
}

// The synthetic fields: a name, a list field, a number and a blank-for-now field
export const SYNTHETIC_FIELDS: RunField[] = [
  makeField({ key: "item_name", column: "Item Name", requirement: "required", is_record_name: true }),
  makeField({
    key: "storage",
    column: "Storage",
    has_lookup_list: true,
    allowed_values: ["Room shelf", "Fridge 2-8", "Freezer minus 20", "Fridge door"],
  }),
  makeField({ key: "amount", column: "Amount", type: "decimal", max_length: 10 }),
  makeField({ key: "later_field", column: "Later Field", role: "blank_for_now" }),
];

/** Return the run's field list with the synthetic fields. */
export function makeFieldList(): RunFieldList {
  return { field_rules_version: "synthetic-1", lookup_lists_version: "v-synthetic", fields: SYNTHETIC_FIELDS };
}

/** Return a synthetic issue summary, changed by `overrides`. */
export function makeIssue(overrides: Partial<IssueSummary> = {}): IssueSummary {
  return {
    issue_id: "iss_0001",
    code: "NOT_IN_LOOKUP",
    severity: "error",
    status: "open",
    message: "Synthetic message.",
    individual_review: false,
    note_required: false,
    sources: [],
    ...overrides,
  };
}

/** Return a synthetic cell, changed by `overrides`. */
export function makeCell(overrides: Partial<ReviewCell> = {}): ReviewCell {
  return {
    field: "item_name",
    column: "Item Name",
    value: null,
    display_value: null,
    written_value: null,
    origin: "extracted",
    extraction_status: "found",
    is_placeholder: false,
    color: "none",
    issues: [],
    sources: [],
    alternatives: [],
    ...overrides,
  };
}

/** Return a source location of a synthetic document chunk. */
export function makeLocation(chunkId: string, overrides: Record<string, unknown> = {}) {
  return { chunk_id: chunkId, document_id: "doc01", file_name: "synthetic_method.docx", section: "5.1 Materials", page: null, sheet: null, row_range: null, is_scanned: false, ...overrides };
}

/** Return a synthetic row with one cell per synthetic field; `cells` replaces cells by field. */
export function makeRow(recordId: string, name: string, cells: Partial<Record<string, Partial<ReviewCell>>> = {}, overrides: Partial<ReviewRow> = {}): ReviewRow {
  const base: Record<string, ReviewCell> = {
    item_name: makeCell({ field: "item_name", column: "Item Name", value: name, display_value: name }),
    storage: makeCell({ field: "storage", column: "Storage", value: "Room shelf", display_value: "Room shelf" }),
    amount: makeCell({ field: "amount", column: "Amount", value: "5", display_value: "5" }),
    later_field: makeCell({ field: "later_field", column: "Later Field", origin: "blank_for_now", extraction_status: null, is_placeholder: true, display_value: "SYNTHETIC PLACEHOLDER", color: "grey" }),
  };
  return {
    record_id: recordId,
    name,
    action_needed: "none",
    found_in: [makeLocation(`${recordId}-c1`)],
    exclusion: null,
    record_issues: [],
    cells: SYNTHETIC_FIELDS.map((field) => ({ ...base[field.key], ...cells[field.key] })),
    ...overrides,
  };
}

/**
 * Return the progress counts as the API makes them: red and yellow issues of included records
 * and the run, any status (total), and those accepted or resolved (resolved).
 */
export function countProgress(rows: ReviewRow[], runIssues: IssueSummary[]) {
  const included = rows.filter((row) => row.exclusion === null);
  const issues = [...included.flatMap((row) => [...row.record_issues, ...row.cells.flatMap((cell) => cell.issues)]), ...runIssues];
  const counted = issues.filter((issue) => issue.severity !== "info");
  const resolved = counted.filter((issue) => issue.status === "accepted" || issue.status === "resolved");
  return { resolved_issues: resolved.length, total_issues: counted.length };
}

/** Return a synthetic view of rows, with issue counts that match them roughly and exact progress. */
export function makeView(rows: ReviewRow[], runIssues: IssueSummary[] = []): ReviewView {
  return {
    rows,
    run_issues: runIssues,
    counts: { records: rows.length, to_fix: 1, to_check: 1, excluded: 0, open_errors: 1, open_warnings: 1, ...countProgress(rows, runIssues) },
  };
}

/** One recorded request: method, path (without /api), query string and parsed JSON body (or null). */
export interface RecordedCall {
  method: string;
  path: string;
  query: string;
  body: unknown;
}

/** An answer: JSON with a status, or a raw Response (for images). */
export type ReviewAnswer = { status: number; body: unknown } | Response;

/** Make a fetch mock that records every call and answers through the handler. */
export function makeRecordingFetch(handler: (method: string, path: string, body: unknown) => ReviewAnswer) {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/api/, "");
    const text = request.method === "GET" ? "" : await request.clone().text();
    const body = text.length > 0 ? JSON.parse(text) : null;
    calls.push({ method: request.method, path, query: url.search, body });
    const answer = handler(request.method, path, body);
    if (answer instanceof Response) return answer;
    return new Response(JSON.stringify(answer.body), { status: answer.status, headers: { "Content-Type": "application/json" } });
  });
  return { fetchMock, calls };
}

/** Return a handler for the standard review reads of run_0001, with `extra` tried first. */
export function makeReviewHandler(
  getView: () => ReviewView,
  extra: (method: string, path: string, body: unknown) => ReviewAnswer | null = () => null,
) {
  return (method: string, path: string, body: unknown): ReviewAnswer => {
    const answer = extra(method, path, body);
    if (answer !== null) return answer;
    if (path === "/runs/run_0001") return { status: 200, body: makeRunDetail({ status: "in_review", current_step: null }) };
    if (path === "/runs/run_0001/records") return { status: 200, body: getView() };
    if (path === "/runs/run_0001/fields") return { status: 200, body: makeFieldList() };
    if (path.startsWith("/runs/run_0001/records/")) return { status: 200, body: { record: {}, issues: [], sources: [] } };
    if (path === "/runs/run_0001/changes") return { status: 200, body: { saved_change_ids: [], ignored_change_ids: [] } };
    if (path === "/runs/run_0001/recheck") return { status: 200, body: { applied_change_ids: [], counts: getView().counts, judge_calls_made: 0 } };
    if (path === "/runs/run_0001/bulk-preview") return { status: 200, body: makeEmptyPreview() };
    if (path === "/runs/run_0001/bulk-actions") return { status: 200, body: [] };
    return { status: 404, body: { error: { code: "NOT_FOUND", message: `No mock for ${method} ${path}.`, details: {} } } };
  };
}

/** Return a bulk preview that matches no record (the default answer of the mocked API). */
export function makeEmptyPreview() {
  return { mode: "change_all", issue_id: null, code: null, field: null, value: null, count: 0, matches: [] };
}
