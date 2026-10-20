// What the Verify dialog shows (UI_SPEC §4.4): the open issues that block Verify (red ones,
// and warnings that need individual review) and the other warnings Verify would accept.
// Built from the review view, or from the issues the API returned when it refused to verify.
import type { RunIssue, VerifyResult, ReviewView } from "../api/types";
import { listOpenIssues, type IssueRef } from "./reviewIssues";

/** The open issues of a run, grouped as the Verify dialog shows them. */
export interface VerifyCheck {
  errors: IssueRef[];
  individualWarnings: IssueRef[];
  otherWarnings: IssueRef[];
}

/** Return true when nothing is open: Verify runs without the dialog. */
export function isClear(check: VerifyCheck): boolean {
  return check.errors.length + check.individualWarnings.length + check.otherWarnings.length === 0;
}

/** Return true when something blocks Verify (red issues or individual-review warnings). */
export function isBlocked(check: VerifyCheck): boolean {
  return check.errors.length > 0 || check.individualWarnings.length > 0;
}

/** Group the view's open red and yellow issues (excluded records left out, run issues included). */
export function checkView(view: ReviewView): VerifyCheck {
  const open = listOpenIssues(view, new Set());
  return {
    errors: open.filter((ref) => ref.issue.severity === "error"),
    individualWarnings: open.filter((ref) => ref.issue.severity === "warning" && ref.issue.individual_review),
    otherWarnings: open.filter((ref) => ref.issue.severity === "warning" && !ref.issue.individual_review),
  };
}

/** Return an issue reference for an issue of a Verify answer. */
function toIssueRef(issue: RunIssue): IssueRef {
  const summary = {
    issue_id: issue.issue_id,
    code: issue.code,
    severity: issue.severity,
    status: issue.status ?? "open",
    message: issue.message,
    individual_review: issue.individual_review ?? false,
  };
  return { issue: summary, recordId: issue.record_id, field: issue.field };
}

/** Group the blockers of a refused Verify answer (nothing is accepted when it is refused). */
export function checkVerifyResult(result: VerifyResult): VerifyCheck {
  return {
    errors: result.blocking_errors.map(toIssueRef),
    individualWarnings: result.individual_review_warnings.map(toIssueRef),
    otherWarnings: [],
  };
}
