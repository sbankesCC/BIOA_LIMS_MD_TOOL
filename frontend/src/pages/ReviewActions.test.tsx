// Tests for the M13 Review actions: bulk actions with their bulk-preview confirmation list,
// Undo from the API's bulk action list, progress, exclude and restore, the Verify dialog's three
// cases and the verified label, and export with both downloads. All data is synthetic; the API
// is a recording fetch mock.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BulkActionSummary, BulkPreviewMatch, ReviewView, RunDetail } from "../api/types";
import { makeRunDetail, renderApp } from "../test/helpers";
import {
  makeIssue,
  makeRecordingFetch,
  makeReviewHandler,
  makeRow,
  makeView,
  type RecordedCall,
  type ReviewAnswer,
} from "../test/reviewFixtures";

// The Review screen address of the synthetic run
const REVIEW_PATH = "/runs/run_0001/review";

/** A change as the tests read it from a request body. */
type SentChange = Record<string, unknown>;

/** Return the POST calls to a path. */
function findPosts(calls: RecordedCall[], path: string): RecordedCall[] {
  return calls.filter((call) => call.method === "POST" && call.path === path);
}

/** Return the changes of every POST /changes call, in order. */
function readSentChanges(calls: RecordedCall[]): SentChange[][] {
  return findPosts(calls, "/runs/run_0001/changes").map((call) => (call.body as { changes: SentChange[] }).changes);
}

/** Return the query parameters of every bulk-preview call. */
function readPreviewQueries(calls: RecordedCall[]): Record<string, string>[] {
  return calls.filter((call) => call.path === "/runs/run_0001/bulk-preview").map((call) => Object.fromEntries(new URLSearchParams(call.query)));
}

/** Return a bulk preview answer with these matches. */
function makePreview(mode: string, matches: BulkPreviewMatch[], field: string | null = null): ReviewAnswer {
  return { status: 200, body: { mode, issue_id: null, code: null, field, value: null, count: matches.length, matches } };
}

/** Return a run in review, changed by `overrides`. */
function makeReviewRun(overrides: Partial<RunDetail> = {}): RunDetail {
  return makeRunDetail({ status: "in_review", current_step: null, ...overrides });
}

/** Open the panel on the first grid cell whose accessible name matches `name` (record 1's). */
async function openCell(name: RegExp) {
  fireEvent.click((await screen.findAllByRole("button", { name }))[0]);
  return screen.findByRole("complementary", { name: "Resolution panel" });
}

/** Three records whose Amount is "five" with the same red number issue. */
function makeAmountView(): ReviewView {
  const rows = ["1", "2", "3"].map((n) =>
    makeRow(`rec_000${n}`, `Synthetic Item ${n}`, {
      amount: { value: "five", display_value: "five", color: "red", issues: [makeIssue({ issue_id: `iss_a${n}`, code: "WRONG_TYPE", severity: "error", message: "Amount must be a number." })] },
    }, { action_needed: "fix" }),
  );
  return makeView(rows);
}

/** The change_all preview of the amount issue: all three records. */
const AMOUNT_MATCHES: BulkPreviewMatch[] = ["1", "2", "3"].map((n) => ({ record_id: `rec_000${n}`, name: `Synthetic Item ${n}`, issue_id: `iss_a${n}`, value: "five", alternative_index: null }));

/** Run "Change all" on the amount issue with record 3 unchecked; returns the recorded calls. */
async function runChangeAll() {
  const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeAmountView, (_method, path) =>
    path === "/runs/run_0001/bulk-preview" ? makePreview("change_all", AMOUNT_MATCHES, "amount") : null,
  ));
  renderApp(REVIEW_PATH, fetchMock);
  const panel = await openCell(/^Amount: five/);
  fireEvent.change(within(panel).getByLabelText("Amount"), { target: { value: "5" } });
  expect(await within(panel).findByText("Also applies to 2 other records with the same issue and value.")).not.toBeNull();
  fireEvent.click(within(panel).getByRole("button", { name: "Change all 3…" }));
  const dialog = await screen.findByRole("dialog", { name: /Change all: set Amount to “5”/ });
  expect(within(dialog).getAllByRole("checkbox").every((box) => (box as HTMLInputElement).checked)).toBe(true);
  expect(within(dialog).getByText(/3 of 3 selected/)).not.toBeNull();
  // Uncheck one record: it is left out of the change
  fireEvent.click(within(dialog).getByRole("checkbox", { name: /Synthetic Item 3/ }));
  expect(within(dialog).getByText(/2 of 3 selected/)).not.toBeNull();
  fireEvent.click(within(dialog).getByRole("button", { name: "Apply to 2 records" }));
  await waitFor(() => expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(1));
  return calls;
}

describe("Bulk actions", () => {
  it("Change all previews with change_all and sends one bulk set_value list, then re-checks", async () => {
    const calls = await runChangeAll();
    expect(readPreviewQueries(calls)).toContainEqual({ mode: "change_all", issue_id: "iss_a1" });
    const [changes] = readSentChanges(calls);
    expect(changes).toHaveLength(2);
    expect(changes.map((change) => change.record_id)).toEqual(["rec_0001", "rec_0002"]);
    for (const change of changes) {
      expect(change).toMatchObject({ type: "set_value", field: "amount", value: "5", reason: null });
    }
    // One bulk ID shared by every change; each change has its own change ID
    expect(String(changes[0].bulk_id)).toMatch(/^blk_[0-9a-f]{32}$/);
    expect(changes[1].bulk_id).toBe(changes[0].bulk_id);
    expect(changes[0].change_id).not.toBe(changes[1].change_id);
  });

  it("Fill missing previews with fill_missing and asks a reason for values without an issue", async () => {
    const issue = makeIssue({ issue_id: "iss_s1", code: "NOT_IN_LOOKUP", severity: "error" });
    const view = makeView([
      makeRow("rec_0001", "Synthetic Item 1", { storage: { value: null, display_value: null, written_value: "two to eight", color: "red", issues: [issue] } }, { action_needed: "fix" }),
      makeRow("rec_0002", "Synthetic Item 2", { storage: { value: null, display_value: null } }),
    ]);
    const matches: BulkPreviewMatch[] = [
      { record_id: "rec_0001", name: "Synthetic Item 1", issue_id: "iss_s1", value: null },
      { record_id: "rec_0002", name: "Synthetic Item 2", issue_id: null, value: null },
    ];
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) =>
      path === "/runs/run_0001/bulk-preview" ? makePreview("fill_missing", matches, "storage") : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Storage: choose from list/);
    expect(await within(panel).findByText("Storage is missing in 2 records. Choose a value above to set all of them.")).not.toBeNull();
    const box = within(panel).getByRole("combobox");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "Fridge 2-8" } });
    fireEvent.mouseDown(within(panel).getByRole("option", { name: "Fridge 2-8" }));
    expect(within(panel).getByText("Storage is missing in 2 records. Set all to “Fridge 2-8”?")).not.toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "Fill all 2…" }));
    const dialog = await screen.findByRole("dialog");
    const apply = within(dialog).getByRole("button", { name: "Apply to 2 records" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Same storage for every synthetic item." } });
    expect(apply.disabled).toBe(false);
    fireEvent.click(apply);
    await waitFor(() => expect(readSentChanges(calls)).toHaveLength(1));
    expect(readPreviewQueries(calls)).toContainEqual({ mode: "fill_missing", field: "storage" });
    const [changes] = readSentChanges(calls);
    expect(changes.map((change) => change.record_id)).toEqual(["rec_0001", "rec_0002"]);
    expect(changes[1]).toMatchObject({ type: "set_value", field: "storage", value: "Fridge 2-8", reason: "Same storage for every synthetic item.", bulk_id: changes[0].bulk_id });
  });

  it("Accept all of a type previews with accept_type and accepts each matched warning", async () => {
    const view = makeView(["1", "2"].map((n) =>
      makeRow(`rec_000${n}`, `Synthetic Item ${n}`, {
        amount: { color: "yellow", issues: [makeIssue({ issue_id: `iss_d${n}`, code: "DEFAULT_APPLIED", severity: "warning" })] },
      }, { action_needed: "check" }),
    ));
    const matches: BulkPreviewMatch[] = ["1", "2"].map((n) => ({ record_id: `rec_000${n}`, name: `Synthetic Item ${n}`, issue_id: `iss_d${n}`, value: "5" }));
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) =>
      path === "/runs/run_0001/bulk-preview" ? makePreview("accept_type", matches) : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Amount: 5, check/);
    expect(await within(panel).findByText("2 open “Default applied” warnings in this run.")).not.toBeNull();
    fireEvent.click(within(panel).getByRole("button", { name: "Accept all 2…" }));
    const dialog = await screen.findByRole("dialog", { name: "Accept all “Default applied” warnings" });
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply to 2 records" }));
    await waitFor(() => expect(readSentChanges(calls)).toHaveLength(1));
    expect(readPreviewQueries(calls)).toContainEqual({ mode: "accept_type", issue_id: "iss_d1" });
    const [changes] = readSentChanges(calls);
    expect(changes.map((change) => change.issue_id)).toEqual(["iss_d1", "iss_d2"]);
    expect(changes[0]).toMatchObject({ type: "accept_warning", source_viewed: false, note: null });
    expect(changes[1].bulk_id).toBe(changes[0].bulk_id);
  });

  it("Resolve repeated conflicts previews with the chosen alternative and picks each record's own index", async () => {
    const alternatives = [
      { index: 0, value: "Fridge 2-8", sources: [] },
      { index: 1, value: "Room shelf", sources: [] },
    ];
    const issue = makeIssue({ issue_id: "iss_c1", code: "CONFLICT_UNRESOLVED", severity: "error" });
    const view = makeView([
      makeRow("rec_0001", "Synthetic Item 1", { storage: { value: null, display_value: null, extraction_status: "conflicting", color: "red", alternatives, issues: [issue] } }, { action_needed: "fix" }),
    ]);
    const matches: BulkPreviewMatch[] = [
      { record_id: "rec_0001", name: "Synthetic Item 1", issue_id: "iss_c1", value: null, alternative_index: 0 },
      { record_id: "rec_0002", name: "Synthetic Item 2", issue_id: "iss_c2", value: null, alternative_index: 1 },
    ];
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) =>
      path === "/runs/run_0001/bulk-preview" ? makePreview("resolve_conflicts", matches, "storage") : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Storage: 2 values/);
    // No offer until an alternative is chosen
    expect(readPreviewQueries(calls)).toHaveLength(0);
    fireEvent.click(within(panel).getByRole("radio", { name: /Fridge 2-8/ }));
    expect(await within(panel).findByText("Use “Fridge 2-8” for all 2 similar conflicts.")).not.toBeNull();
    expect(readPreviewQueries(calls)).toContainEqual({ mode: "resolve_conflicts", issue_id: "iss_c1", alternative_index: "0" });
    fireEvent.click(within(panel).getByRole("button", { name: "Resolve all 2…" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Apply to 2 records" }));
    await waitFor(() => expect(readSentChanges(calls)).toHaveLength(1));
    const [changes] = readSentChanges(calls);
    expect(changes[0]).toMatchObject({ type: "pick_alternative", record_id: "rec_0001", field: "storage", alternative_index: 0 });
    expect(changes[1]).toMatchObject({ type: "pick_alternative", record_id: "rec_0002", field: "storage", alternative_index: 1, bulk_id: changes[0].bulk_id });
  });

  it("an individual-review warning offers no bulk action and asks for no preview", async () => {
    const view = makeView(["1", "2"].map((n) =>
      makeRow(`rec_000${n}`, `Synthetic Item ${n}`, {
        amount: { color: "yellow", issues: [makeIssue({ issue_id: `iss_v${n}`, code: "CITATION_NOT_VERIFIED", severity: "warning", individual_review: true })] },
      }, { action_needed: "check" }),
    ));
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Amount: 5, check/);
    expect(within(panel).getByRole("heading", { name: "Amount · Citation not verified" })).not.toBeNull();
    expect(within(panel).queryByRole("button", { name: /Accept all/ })).toBeNull();
    expect(readPreviewQueries(calls)).toHaveLength(0);
  });

  it("shows the API's message when a bulk accept is refused", async () => {
    const view = makeView(["1", "2"].map((n) =>
      makeRow(`rec_000${n}`, `Synthetic Item ${n}`, {
        amount: { color: "yellow", issues: [makeIssue({ issue_id: `iss_d${n}`, code: "DEFAULT_APPLIED", severity: "warning" })] },
      }, { action_needed: "check" }),
    ));
    const matches: BulkPreviewMatch[] = ["1", "2"].map((n) => ({ record_id: `rec_000${n}`, name: `Synthetic Item ${n}`, issue_id: `iss_d${n}`, value: "5" }));
    const refusal = "This warning must be reviewed on its own, so it cannot be part of a bulk action. Open its source and accept it by itself.";
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view, (method, path) => {
      if (path === "/runs/run_0001/bulk-preview") return makePreview("accept_type", matches);
      if (method === "POST" && path === "/runs/run_0001/changes") return { status: 409, body: { error: { code: "BULK_ACCEPT_NOT_ALLOWED", message: refusal, details: {} } } };
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Amount: 5, check/);
    fireEvent.click(await within(panel).findByRole("button", { name: "Accept all 2…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply to 2 records" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain(refusal);
  });
});

/** Return a synthetic bulk action of the list, changed by `overrides`. */
function makeBulkAction(overrides: Partial<BulkActionSummary> = {}): BulkActionSummary {
  return {
    bulk_id: "blk_synthetic_1",
    change_type: "set_value",
    field: "amount",
    issue_code: null,
    record_count: 2,
    change_count: 2,
    created_by: "synthetic-reviewer",
    created_at: "2026-10-16T09:30:00Z",
    is_pending: false,
    is_undone: false,
    undone_by: null,
    undone_at: null,
    can_undo: true,
    ...overrides,
  };
}

describe("Undo", () => {
  it("offers Undo from the API's bulk action list after a bulk action, and reads the list again after undo", async () => {
    let bulkId: string | null = null;
    let isUndone = false;
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeAmountView, (method, path, body) => {
      if (path === "/runs/run_0001/bulk-preview") return makePreview("change_all", AMOUNT_MATCHES, "amount");
      // The API's list follows the saved changes: the bulk action, then its undo
      if (method === "POST" && path === "/runs/run_0001/changes") {
        const [first] = (body as { changes: SentChange[] }).changes;
        if (first.type === "undo_bulk") isUndone = true;
        else bulkId = String(first.bulk_id);
      }
      if (path === "/runs/run_0001/bulk-actions") {
        const list = bulkId === null ? [] : [makeBulkAction({ bulk_id: bulkId, is_undone: isUndone, can_undo: !isUndone })];
        return { status: 200, body: list };
      }
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Amount: five/);
    // No bulk action yet: no Undo
    expect(screen.queryByText(/Last bulk action/)).toBeNull();
    fireEvent.change(within(panel).getByLabelText("Amount"), { target: { value: "5" } });
    fireEvent.click(await within(panel).findByRole("button", { name: "Change all 3…" }));
    const dialog = await screen.findByRole("dialog", { name: /Change all/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Apply to 3 records" }));
    // After the bulk action's re-check, the reloaded list offers its Undo
    expect(await screen.findByText(/Last bulk action: Set Amount in 2 records · synthetic-reviewer/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Undo: Set Amount in 2 records" }));
    await waitFor(() => expect(readSentChanges(calls)).toHaveLength(2));
    expect(readSentChanges(calls)[1]).toEqual([expect.objectContaining({ type: "undo_bulk", bulk_id: bulkId })]);
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(2));
    // The list read after the undo says it can no longer be undone
    await waitFor(() => expect(screen.queryByText(/Last bulk action/)).toBeNull());
  });

  it("lists only bulk actions with can_undo: the newest first, earlier ones folded", async () => {
    const actions = [
      makeBulkAction({ bulk_id: "blk_3", change_type: "accept_warning", field: null, issue_code: "DEFAULT_APPLIED", record_count: 4, change_count: 4 }),
      makeBulkAction({ bulk_id: "blk_2", is_undone: true, can_undo: false, undone_by: "synthetic-reviewer", undone_at: "2026-10-16T09:40:00Z" }),
      makeBulkAction({ bulk_id: "blk_1", change_type: "pick_alternative", field: "storage", record_count: 1, change_count: 1 }),
    ];
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeAmountView, (_method, path) =>
      path === "/runs/run_0001/bulk-actions" ? { status: 200, body: actions } : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText(/Last bulk action: Accepted “Default applied” warnings in 4 records/)).not.toBeNull();
    expect(screen.getByText("Earlier bulk actions you can undo (1)")).not.toBeNull();
    // The undone one is not offered
    expect(screen.getAllByRole("button", { name: /^Undo:/ })).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "Undo: Resolved Storage conflicts in 1 record" }));
    await waitFor(() => expect(readSentChanges(calls)).toEqual([[expect.objectContaining({ type: "undo_bulk", bulk_id: "blk_1" })]]));
  });

  it("reads the list again after exclude and its re-check", async () => {
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeAmountView));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Amount: five/);
    const listReads = () => calls.filter((call) => call.method === "GET" && call.path === "/runs/run_0001/bulk-actions").length;
    await waitFor(() => expect(listReads()).toBeGreaterThanOrEqual(1));
    const before = listReads();
    fireEvent.click(within(panel).getByRole("button", { name: "Exclude record" }));
    const dialog = await screen.findByRole("dialog", { name: "Exclude record" });
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Synthetic reason" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Exclude record" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(1));
    await waitFor(() => expect(listReads()).toBeGreaterThan(before));
  });
});

describe("Progress", () => {
  it("shows issues resolved from the API's counts", async () => {
    const view = makeView([
      makeRow("rec_0001", "Synthetic Item 1", {
        amount: { issues: [makeIssue({ issue_id: "iss_p1", code: "DEFAULT_APPLIED", severity: "warning", status: "accepted" }), makeIssue({ issue_id: "iss_p2", code: "FORMAT_CORRECTED", severity: "info" })] },
      }),
      makeRow("rec_0002", "Synthetic Item 2", { storage: { color: "red", issues: [makeIssue({ issue_id: "iss_p3" })] } }, { action_needed: "fix" }),
    ], [makeIssue({ issue_id: "iss_p4", code: "SCANNED_PAGES", severity: "warning" })]);
    // Grey issues are not counted: 1 of 3 red and yellow issues is resolved
    expect(view.counts).toMatchObject({ resolved_issues: 1, total_issues: 3 });
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText("Issues resolved: 1 of 3")).not.toBeNull();
    const bar = screen.getByRole("progressbar", { name: "Issues resolved" });
    expect(bar.getAttribute("aria-valuenow")).toBe("1");
    expect(bar.getAttribute("aria-valuemax")).toBe("3");
    expect(screen.queryByText(/Records ready/)).toBeNull();
  });
});

describe("Exclude and restore", () => {
  it("Exclude record needs a reason, then sends exclude_record and re-checks", async () => {
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeAmountView));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openCell(/^Amount: five/);
    fireEvent.click(within(panel).getByRole("button", { name: "Exclude record" }));
    const dialog = await screen.findByRole("dialog", { name: "Exclude record" });
    const confirm = within(dialog).getByRole("button", { name: "Exclude record" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    // Spaces alone are not a reason
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "   " } });
    expect(confirm.disabled).toBe(true);
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: " Synthetic equipment, not a consumable " } });
    fireEvent.click(confirm);
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(1));
    expect(readSentChanges(calls)[0]).toEqual([expect.objectContaining({ type: "exclude_record", record_id: "rec_0001", reason: "Synthetic equipment, not a consumable" })]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("Restore on an excluded row sends restore_record and re-checks", async () => {
    const view = makeAmountView();
    view.rows.push(makeRow("rec_0009", "Synthetic Plate C", {}, { action_needed: "excluded", exclusion: { by: "tester", at: "2026-10-16T09:00:00Z", reason: "synthetic reason" } }));
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Restore: Synthetic Plate C" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(1));
    expect(readSentChanges(calls)[0]).toEqual([expect.objectContaining({ type: "restore_record", record_id: "rec_0009" })]);
  });
});

describe("Verify", () => {
  it("is blocked by red issues and individual-review warnings, which are listed and open the issue", async () => {
    const view = makeView([
      makeRow("rec_0001", "Synthetic Item 1", { amount: { value: "five", display_value: "five", color: "red", issues: [makeIssue({ issue_id: "iss_red", code: "WRONG_TYPE", severity: "error" })] } }, { action_needed: "fix" }),
      makeRow("rec_0002", "Synthetic Item 2", { amount: { color: "yellow", issues: [makeIssue({ issue_id: "iss_cite", code: "CITATION_NOT_VERIFIED", severity: "warning", individual_review: true })] } }, { action_needed: "check" }),
    ]);
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Verify output" }));
    const dialog = await screen.findByRole("dialog", { name: "Your review isn't finished" });
    expect(within(dialog).getByText("1 issue to fix.")).not.toBeNull();
    expect(within(dialog).getByText("1 warning must be reviewed one at a time.")).not.toBeNull();
    expect(within(dialog).getByText(/Before importing into production LabVantage/)).not.toBeNull();
    expect((within(dialog).getByRole("button", { name: "Accept warnings and verify" }) as HTMLButtonElement).disabled).toBe(true);
    // A listed blocker opens its issue in the panel
    fireEvent.click(within(dialog).getByRole("button", { name: /Synthetic Item 2 · Amount · Citation not verified/ }));
    const panel = await screen.findByRole("complementary", { name: "Resolution panel" });
    expect(within(panel).getByRole("heading", { name: "Synthetic Item 2" })).not.toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(findPosts(calls, "/runs/run_0001/verify")).toHaveLength(0);
  });

  it("with only other warnings, the verifier accepts them and the verified label shows", async () => {
    let isVerified = false;
    const view = makeView([
      makeRow("rec_0001", "Synthetic Item 1", { amount: { color: "yellow", issues: [makeIssue({ issue_id: "iss_def", code: "DEFAULT_APPLIED", severity: "warning" })] } }, { action_needed: "check" }),
    ]);
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (method, path) => {
      if (path === "/runs/run_0001") return { status: 200, body: makeReviewRun(isVerified ? { is_verified: true, verified_by: "synthetic-verifier", verified_at: "2026-10-16T10:00:00Z" } : {}) };
      if (method === "POST" && path === "/runs/run_0001/verify") {
        isVerified = true;
        return { status: 200, body: { is_verified: true, blocking_errors: [], individual_review_warnings: [], accepted_warnings: [], counts: view.counts } };
      }
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText("Not verified yet: exports are saved as drafts")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Verify output" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("1 warning not reviewed.")).not.toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "Accept warnings and verify" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/verify")).toHaveLength(1));
    expect(await screen.findByText(/^Verified by synthetic-verifier on /)).not.toBeNull();
    expect(screen.getByText("Run · Verified by synthetic-verifier")).not.toBeNull();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("with nothing open, verifies at once; a refusal lists the API's blockers", async () => {
    const view = makeView([makeRow("rec_0001", "Synthetic Item 1")]);
    const blocker = { issue_id: "iss_new", code: "WRONG_TYPE", severity: "error", record_id: "rec_0001", field: "amount", message: "Amount must be a number.", individual_review: false, details: {}, status: "open", closed_by: null };
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (method, path) =>
      method === "POST" && path === "/runs/run_0001/verify"
        ? { status: 200, body: { is_verified: false, blocking_errors: [blocker], individual_review_warnings: [], accepted_warnings: [], counts: view.counts } }
        : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Verify output" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/verify")).toHaveLength(1));
    const dialog = await screen.findByRole("dialog", { name: "Your review isn't finished" });
    expect(await within(dialog).findByText("1 issue to fix.")).not.toBeNull();
    expect(within(dialog).getByRole("button", { name: /Synthetic Item 1 · Amount · Not a number/ })).not.toBeNull();
  });

  it("a later change removes the verified label", async () => {
    let hasChanged = false;
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeAmountView, (method, path) => {
      if (path === "/runs/run_0001") return { status: 200, body: makeReviewRun(hasChanged ? {} : { is_verified: true, verified_by: "synthetic-verifier", verified_at: "2026-10-16T10:00:00Z" }) };
      if (method === "POST" && path === "/runs/run_0001/changes") hasChanged = true;
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText("Run · Verified by synthetic-verifier")).not.toBeNull();
    const panel = await openCell(/^Amount: five/);
    fireEvent.change(within(panel).getByLabelText("Amount"), { target: { value: "5" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Save and next issue" }));
    expect(await screen.findByText("Run · In review")).not.toBeNull();
    expect(screen.getByText("Not verified yet: exports are saved as drafts")).not.toBeNull();
  });
});

describe("Export", () => {
  let savedNames: string[] = [];

  beforeEach(() => {
    savedNames = [];
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic-file"), revokeObjectURL: vi.fn() }));
    // Record each file the screen saves instead of downloading it
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      savedNames.push(this.download);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("creates the export, downloads both files with their display names and shows the post-export state", async () => {
    const created = { export_id: "exp_0002", number: 2, is_draft: true, loader_file_name: "Synthetic run – export 2 – draft.xlsx", audit_file_name: "Synthetic run – export 2 – audit – draft.xlsx", exported_at: "2026-10-16T11:00:00Z", exported_by: "synthetic-user" };
    const earlier = { ...created, export_id: "exp_0001", number: 1, loader_file_name: "Synthetic run – export 1 – draft.xlsx", audit_file_name: "Synthetic run – export 1 – audit – draft.xlsx" };
    let hasExported = false;
    const workbook = () => new Response(new Blob(["synthetic"]), { status: 200, headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" } });
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeAmountView, (method, path) => {
      if (path === "/runs/run_0001") return { status: 200, body: makeReviewRun({ exports: hasExported ? [earlier, created] : [earlier] }) };
      if (method === "POST" && path === "/runs/run_0001/exports") {
        hasExported = true;
        return { status: 201, body: created };
      }
      if (path === "/runs/run_0001/exports/exp_0002/loader" || path === "/runs/run_0001/exports/exp_0002/audit") return workbook();
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Export to Excel" }));
    await waitFor(() => expect(savedNames).toEqual([created.loader_file_name, created.audit_file_name]));
    expect(findPosts(calls, "/runs/run_0001/exports")).toHaveLength(1);
    expect(calls.some((call) => call.path === "/runs/run_0001/exports/exp_0002/loader")).toBe(true);
    expect(calls.some((call) => call.path === "/runs/run_0001/exports/exp_0002/audit")).toBe(true);
    expect(await screen.findByText("Export 2 saved as a draft (not verified).")).not.toBeNull();
    // Each file can be downloaded again; the earlier export stays listed
    fireEvent.click(screen.getByRole("button", { name: `Audit workbook: ${created.audit_file_name}` }));
    await waitFor(() => expect(savedNames).toHaveLength(3));
    expect(savedNames[2]).toBe(created.audit_file_name);
    expect(screen.getByText("Earlier exports (1)")).not.toBeNull();
  });

  it("shows the API's message when the export fails", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeAmountView, (method, path) =>
      method === "POST" && path === "/runs/run_0001/exports"
        ? { status: 503, body: { error: { code: "SETTING_MISSING", message: "Set STORAGE_DIR in .env, then restart the app.", details: { setting: "STORAGE_DIR" } } } }
        : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Export to Excel" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Set STORAGE_DIR in .env");
    expect(savedNames).toHaveLength(0);
  });
});
