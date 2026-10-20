// Bulk actions of the resolution panel (UI_SPEC §4.3 "Bulk actions"): which ones an issue
// offers, the bulk-preview request of each, and the one bulk change list sent after the user
// confirms (CONTRACTS §6: every change shares one bulk_id, so the action is undone together).
import type { BulkPreviewRequest } from "../api/review";
import type { BulkMode, BulkPreviewMatch, ReviewCell, ReviewRow } from "../api/types";
import type { IssueChoice, NewChange } from "./issueActions";
import { findCell, type IssueRef } from "./reviewIssues";

/** A bulk action the panel can offer for the selected issue. */
export interface BulkOffer {
  mode: BulkMode;
  // The bulk-preview request of this action
  request: BulkPreviewRequest;
  // The value to set (change all, fill missing) or the chosen alternative's value (conflicts);
  // null while the user has not chosen it yet
  value: string | null;
  // The column the action works on ("Record" for a record-level issue)
  column: string;
  // The selected issue and its record, to tell the other records apart in the preview
  issueId: string;
  recordId: string;
}

/** What the offers are built from: the selected issue, its record and the user's current choice. */
export interface BulkOfferContext {
  issue: IssueRef;
  row: ReviewRow | null;
  choice: IssueChoice | null;
}

// Origins of values the tool never changes (placeholders and system values)
const FIXED_ORIGINS = new Set<ReviewCell["origin"]>(["blank_for_now", "system"]);

/** Return true when a cell has no value (null or blank). */
function isMissing(cell: ReviewCell): boolean {
  return cell.value === null || cell.value.trim().length === 0;
}

/** Return the value a set_value choice writes on this field, or null (no choice, or "not found"). */
function readChosenValue(choice: IssueChoice | null, recordId: string, field: string): string | null {
  if (choice === null || choice.kind !== "change" || choice.change.type !== "set_value") return null;
  const change = choice.change;
  return change.record_id === recordId && change.field === field ? change.value : null;
}

/** Return the alternative index a pick_alternative choice picks on this field, or null. */
function readChosenAlternative(choice: IssueChoice | null, recordId: string, field: string): number | null {
  if (choice === null || choice.kind !== "change" || choice.change.type !== "pick_alternative") return null;
  const change = choice.change;
  return change.record_id === recordId && change.field === field ? change.alternative_index : null;
}

/** Return the value offer of a field issue: resolve conflicts, fill missing or change all. */
function findValueOffer(ref: IssueRef, recordId: string, cell: ReviewCell, choice: IssueChoice | null): BulkOffer | null {
  const field = cell.field;
  const base = { column: cell.column, issueId: ref.issue.issue_id, recordId };
  // A conflict: use the chosen alternative in every conflict with the same values
  if (cell.extraction_status === "conflicting" && cell.alternatives.length > 0) {
    const index = readChosenAlternative(choice, recordId, field);
    if (index === null) return null;
    const value = cell.alternatives.find((alternative) => alternative.index === index)?.value ?? null;
    return { ...base, mode: "resolve_conflicts", request: { mode: "resolve_conflicts", issueId: ref.issue.issue_id, alternativeIndex: index }, value };
  }
  const value = readChosenValue(choice, recordId, field);
  // A missing value: fill every record where this field is missing
  if (isMissing(cell)) {
    return { ...base, mode: "fill_missing", request: { mode: "fill_missing", field }, value };
  }
  // Otherwise: change every record with the same issue and the same current value
  return { ...base, mode: "change_all", request: { mode: "change_all", issueId: ref.issue.issue_id }, value };
}

/**
 * Return the bulk actions the selected issue offers. Individual-review warnings offer none
 * (they are reviewed one at a time); only warnings offer "Accept all of this type".
 */
export function findBulkOffers({ issue: ref, row, choice }: BulkOfferContext): BulkOffer[] {
  const { issue } = ref;
  if (row === null || ref.recordId === null || issue.status !== "open" || issue.individual_review) {
    return [];
  }
  const offers: BulkOffer[] = [];
  // A value change applied to the same field of similar records
  const cell = ref.field !== null ? findCell(row, ref.field) : null;
  if (cell !== null && !FIXED_ORIGINS.has(cell.origin) && issue.severity !== "info") {
    const offer = findValueOffer(ref, ref.recordId, cell, choice);
    if (offer !== null) offers.push(offer);
  }
  // Accept every open warning with the same code
  if (issue.severity === "warning") {
    const request: BulkPreviewRequest = { mode: "accept_type", issueId: issue.issue_id };
    offers.push({ mode: "accept_type", request, value: null, column: cell?.column ?? "Record", issueId: issue.issue_id, recordId: ref.recordId });
  }
  return offers;
}

/** Return true when a preview match is the selected issue's own record (or own issue). */
export function isSelectedMatch(offer: BulkOffer, match: BulkPreviewMatch): boolean {
  if (offer.mode === "fill_missing") return match.record_id === offer.recordId;
  return match.issue_id === offer.issueId;
}

/** Return a stable key of a preview match (a record can match once per issue in accept_type). */
export function makeMatchKey(match: BulkPreviewMatch): string {
  return `${match.record_id}|${match.issue_id ?? ""}`;
}

/** Return true when some matches have no open issue, so changing them needs a reason (CONTRACTS §6). */
export function needsReason(offer: BulkOffer, matches: BulkPreviewMatch[]): boolean {
  return offer.mode !== "accept_type" && offer.mode !== "resolve_conflicts" && matches.some((match) => match.issue_id === null);
}

/** Return the change of one match, or null when the match cannot take this action. */
function buildMatchChange(offer: BulkOffer, field: string | null, match: BulkPreviewMatch, bulkId: string, reason: string | null): NewChange | null {
  if (offer.mode === "accept_type") {
    return match.issue_id !== null ? { type: "accept_warning", issue_id: match.issue_id, source_viewed: false, note: null, bulk_id: bulkId } : null;
  }
  if (field === null) return null;
  if (offer.mode === "resolve_conflicts") {
    const index = match.alternative_index ?? null;
    return index !== null ? { type: "pick_alternative", record_id: match.record_id, field, alternative_index: index, bulk_id: bulkId } : null;
  }
  return offer.value !== null ? { type: "set_value", record_id: match.record_id, field, value: offer.value, reason, bulk_id: bulkId } : null;
}

/** Return the bulk change list for the checked matches; every change shares `bulkId`. */
export function buildBulkChanges(offer: BulkOffer, field: string | null, matches: BulkPreviewMatch[], bulkId: string, reason: string | null): NewChange[] {
  return matches.flatMap((match) => {
    const change = buildMatchChange(offer, field, match, bulkId, reason);
    return change !== null ? [change] : [];
  });
}

/** Return the sentence that offers the action, with the number of other records it also touches. */
export function describeOffer(offer: BulkOffer, total: number, others: number, shortLabel: string): string {
  const records = (count: number) => `${count} ${count === 1 ? "record" : "records"}`;
  switch (offer.mode) {
    case "change_all":
      return `Also applies to ${others} other ${others === 1 ? "record" : "records"} with the same issue and value.`;
    case "fill_missing":
      return offer.value !== null
        ? `${offer.column} is missing in ${records(total)}. Set all to “${offer.value}”?`
        : `${offer.column} is missing in ${records(total)}. Choose a value above to set all of them.`;
    case "accept_type":
      return `${total} open “${shortLabel}” ${total === 1 ? "warning" : "warnings"} in this run.`;
    default:
      return `Use “${offer.value ?? ""}” for all ${total} similar conflicts.`;
  }
}

/** Return the label of the button that opens the confirmation list. */
export function describeOfferButton(offer: BulkOffer, total: number): string {
  switch (offer.mode) {
    case "change_all":
      return `Change all ${total}…`;
    case "fill_missing":
      return `Fill all ${total}…`;
    case "accept_type":
      return `Accept all ${total}…`;
    default:
      return `Resolve all ${total}…`;
  }
}

/** Return the confirmation dialog's title. */
export function describeOfferTitle(offer: BulkOffer, shortLabel: string): string {
  switch (offer.mode) {
    case "change_all":
      return `Change all: set ${offer.column} to “${offer.value ?? ""}”`;
    case "fill_missing":
      return `Fill missing: set ${offer.column} to “${offer.value ?? ""}”`;
    case "accept_type":
      return `Accept all “${shortLabel}” warnings`;
    default:
      return `Resolve repeated conflicts: use “${offer.value ?? ""}”`;
  }
}
