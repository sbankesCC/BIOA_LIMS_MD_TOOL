// Tests for the pure M13 helpers: which bulk actions an issue offers, the bulk change list they
// send, and how the Verify dialog groups open issues. Data is synthetic.
import { describe, expect, it } from "vitest";
import type { VerifyResult } from "../api/types";
import { makeIssue, makeRow, makeView } from "../test/reviewFixtures";
import { buildBulkChanges, findBulkOffers, needsReason } from "./bulkActions";
import type { IssueChoice } from "./issueActions";
import { checkVerifyResult, checkView, isBlocked, isClear } from "./verifyCheck";

/** Return a set_value choice for a record's field. */
function setValueChoice(recordId: string, field: string, value: string | null): IssueChoice {
  return { kind: "change", change: { type: "set_value", record_id: recordId, field, value, reason: null } };
}

describe("findBulkOffers", () => {
  it("a red issue on a value offers Change all; a missing value offers Fill missing", () => {
    const issue = makeIssue({ issue_id: "iss_1", code: "WRONG_TYPE" });
    const row = makeRow("rec_1", "Synthetic Item", { amount: { value: "five", issues: [issue] } });
    const offers = findBulkOffers({ issue: { issue, recordId: "rec_1", field: "amount" }, row, choice: setValueChoice("rec_1", "amount", "5") });
    expect(offers.map((offer) => [offer.mode, offer.value])).toEqual([["change_all", "5"]]);
    const missingRow = makeRow("rec_1", "Synthetic Item", { amount: { value: null, issues: [issue] } });
    const missing = findBulkOffers({ issue: { issue, recordId: "rec_1", field: "amount" }, row: missingRow, choice: null });
    expect(missing.map((offer) => [offer.mode, offer.request])).toEqual([["fill_missing", { mode: "fill_missing", field: "amount" }]]);
  });

  it("a warning also offers Accept all of a type; an individual-review warning offers nothing", () => {
    const warning = makeIssue({ issue_id: "iss_2", code: "DEFAULT_APPLIED", severity: "warning" });
    const row = makeRow("rec_1", "Synthetic Item", { amount: { issues: [warning] } });
    const offers = findBulkOffers({ issue: { issue: warning, recordId: "rec_1", field: "amount" }, row, choice: null });
    expect(offers.map((offer) => offer.mode)).toEqual(["change_all", "accept_type"]);
    const individual = { ...warning, individual_review: true };
    expect(findBulkOffers({ issue: { issue: individual, recordId: "rec_1", field: "amount" }, row, choice: null })).toEqual([]);
  });

  it("a conflict offers Resolve repeated conflicts only once an alternative is picked", () => {
    const issue = makeIssue({ issue_id: "iss_3", code: "CONFLICT_UNRESOLVED" });
    const alternatives = [{ index: 0, value: "Synthetic A", sources: [] }, { index: 1, value: "Synthetic B", sources: [] }];
    const row = makeRow("rec_1", "Synthetic Item", { storage: { value: null, extraction_status: "conflicting", alternatives, issues: [issue] } });
    const ref = { issue, recordId: "rec_1", field: "storage" };
    expect(findBulkOffers({ issue: ref, row, choice: null })).toEqual([]);
    const choice: IssueChoice = { kind: "change", change: { type: "pick_alternative", record_id: "rec_1", field: "storage", alternative_index: 1 } };
    const [offer] = findBulkOffers({ issue: ref, row, choice });
    expect(offer.request).toEqual({ mode: "resolve_conflicts", issueId: "iss_3", alternativeIndex: 1 });
    expect(offer.value).toBe("Synthetic B");
  });
});

describe("buildBulkChanges", () => {
  it("fill missing sends one set_value per match with the reason and one bulk ID", () => {
    const issue = makeIssue({ issue_id: "iss_1" });
    const row = makeRow("rec_1", "Synthetic Item", { amount: { value: null, issues: [issue] } });
    const [offer] = findBulkOffers({ issue: { issue, recordId: "rec_1", field: "amount" }, row, choice: setValueChoice("rec_1", "amount", "5") });
    const matches = [
      { record_id: "rec_1", name: "A", issue_id: "iss_1", value: null },
      { record_id: "rec_2", name: "B", issue_id: null, value: null },
    ];
    expect(needsReason(offer, matches)).toBe(true);
    expect(needsReason(offer, matches.slice(0, 1))).toBe(false);
    const changes = buildBulkChanges(offer, "amount", matches, "blk_1", "synthetic reason");
    expect(changes).toEqual([
      { type: "set_value", record_id: "rec_1", field: "amount", value: "5", reason: "synthetic reason", bulk_id: "blk_1" },
      { type: "set_value", record_id: "rec_2", field: "amount", value: "5", reason: "synthetic reason", bulk_id: "blk_1" },
    ]);
  });
});

describe("Verify grouping", () => {
  it("groups open issues of included records into blockers and other warnings", () => {
    const view = makeView([
      makeRow("rec_1", "A", { amount: { issues: [makeIssue({ issue_id: "e", severity: "error" })] } }),
      makeRow("rec_2", "B", { amount: { issues: [makeIssue({ issue_id: "w", severity: "warning" }), makeIssue({ issue_id: "i", severity: "warning", individual_review: true })] } }),
      makeRow("rec_3", "C", { amount: { issues: [makeIssue({ issue_id: "x", severity: "error" })] } }, { exclusion: { by: "t", at: "2026-10-16T09:00:00Z", reason: "r" } }),
      makeRow("rec_4", "D", { amount: { issues: [makeIssue({ issue_id: "g", severity: "info" }), makeIssue({ issue_id: "a", severity: "warning", status: "accepted" })] } }),
    ]);
    const check = checkView(view);
    expect(check.errors.map((ref) => ref.issue.issue_id)).toEqual(["e"]);
    expect(check.individualWarnings.map((ref) => ref.issue.issue_id)).toEqual(["i"]);
    expect(check.otherWarnings.map((ref) => ref.issue.issue_id)).toEqual(["w"]);
    expect(isBlocked(check)).toBe(true);
    expect(isClear(checkView(makeView([makeRow("rec_1", "A")])))).toBe(true);
  });

  it("a refused Verify answer becomes blockers with their record and field", () => {
    const blocker = { issue_id: "e", code: "WRONG_TYPE", severity: "error", record_id: "rec_1", field: "amount", message: "m", individual_review: false, note_required: false, details: {}, status: "open", closed_by: null } as const;
    const result = { is_verified: false, blocking_errors: [blocker], individual_review_warnings: [], accepted_warnings: [], counts: makeView([]).counts } as VerifyResult;
    const check = checkVerifyResult(result);
    expect(check.errors).toEqual([{ issue: { issue_id: "e", code: "WRONG_TYPE", severity: "error", status: "open", message: "m", individual_review: false, note_required: false, sources: [], duplicate_candidates: [] }, recordId: "rec_1", field: "amount" }]);
    expect(isBlocked(check)).toBe(true);
  });
});
