// The actions each issue type offers in the resolution panel (UI_SPEC §4.3 "Issue actions"),
// and how the user's choice becomes a change for POST /runs/{run_id}/changes.
// Issue codes are the tool's catalogue contract (backend validation/codes.py), not client data.
import type { Change, IssueSummary, RunField } from "../api/types";

/** The kinds of action component, one per row of the UI_SPEC issue table. */
export type ActionKind =
  | "enter_value"
  | "pick_alternative"
  | "review_source"
  | "optional_not_found"
  | "accept_or_change"
  | "possible_duplicate"
  | "not_a_consumable"
  | "confirm_with_note"
  | "nothing_to_do";

/** How an issue type is shown: its action kind, a short label for the issue list, its Accept label. */
export interface IssueActionRule {
  kind: ActionKind;
  shortLabel: string;
  acceptLabel?: string;
}

// One rule per catalogue code the UI_SPEC table names; other codes fall back by severity
const RULES_BY_CODE: Record<string, IssueActionRule> = {
  REQUIRED_MISSING: { kind: "enter_value", shortLabel: "Missing" },
  NOT_IN_LOOKUP: { kind: "enter_value", shortLabel: "Not in lookup list" },
  TOO_LONG: { kind: "enter_value", shortLabel: "Too long" },
  WRONG_TYPE: { kind: "enter_value", shortLabel: "Not a number" },
  INVALID_CHARACTERS: { kind: "enter_value", shortLabel: "Characters not allowed" },
  DUPLICATE_IN_RUN: { kind: "enter_value", shortLabel: "Same name as another record" },
  EXISTS_IN_LABVANTAGE: { kind: "enter_value", shortLabel: "Already in LabVantage" },
  CONFLICT_UNRESOLVED: { kind: "pick_alternative", shortLabel: "Conflicting values" },
  CONTRADICTED_BY_SOURCE: { kind: "review_source", shortLabel: "Source says something else" },
  CITATION_NOT_VERIFIED: { kind: "review_source", shortLabel: "Citation not verified" },
  UNSUPPORTED_BY_SOURCE: { kind: "review_source", shortLabel: "Source may not support it" },
  UNREPORTED_CONFLICT: { kind: "review_source", shortLabel: "Another source may differ" },
  SCANNED_SOURCE: { kind: "review_source", shortLabel: "Read from a scanned page" },
  VALUE_PRESENT_MISSED: { kind: "review_source", shortLabel: "May be in the documents" },
  OPTIONAL_NOT_FOUND: { kind: "optional_not_found", shortLabel: "Not found, optional" },
  DEFAULT_APPLIED: { kind: "accept_or_change", shortLabel: "Default applied" },
  OR_EQUIVALENT: { kind: "accept_or_change", shortLabel: "Or equivalent", acceptLabel: "Accept the named product" },
  POSSIBLE_DUPLICATE: { kind: "possible_duplicate", shortLabel: "Possible duplicate" },
  POSSIBLE_DUPLICATE_IN_RUN: { kind: "possible_duplicate", shortLabel: "May repeat another record" },
  NOT_A_CONSUMABLE_TYPE: { kind: "not_a_consumable", shortLabel: "May not be a consumable" },
  RECORD_DROPPED_ON_REEXTRACTION: { kind: "not_a_consumable", shortLabel: "Dropped on re-extraction" },
  SHOULD_BE_SPLIT: { kind: "confirm_with_note", shortLabel: "Should be split" },
  MISSED_CANDIDATES_UNRESOLVED: { kind: "confirm_with_note", shortLabel: "Items may be missing" },
  EXCLUDED_ITEM_CHALLENGED: { kind: "confirm_with_note", shortLabel: "Left-out items to check" },
  FORMAT_CORRECTED: { kind: "nothing_to_do", shortLabel: "Formatting corrected" },
  NUMBER_READ_FROM_TEXT: { kind: "nothing_to_do", shortLabel: "Number read from text" },
};

/** Return the short label of a catalogue code the UI_SPEC table names, or null for other codes. */
export function findShortLabel(code: string): string | null {
  return RULES_BY_CODE[code]?.shortLabel ?? null;
}

/** Return how an issue is handled: by its code, else by its severity and whether it has a field. */
export function findActionRule(issue: IssueSummary, hasField: boolean): IssueActionRule {
  const rule = RULES_BY_CODE[issue.code];
  if (rule !== undefined) {
    return rule;
  }
  // Unknown codes: red fields need a value, yellow ones are accepted or changed, grey ones are information
  if (issue.severity === "error") {
    return hasField ? { kind: "enter_value", shortLabel: "Needs a fix" } : { kind: "nothing_to_do", shortLabel: "Problem" };
  }
  if (issue.severity === "warning") {
    return { kind: "accept_or_change", shortLabel: "Check" };
  }
  return { kind: "nothing_to_do", shortLabel: "Information" };
}

// Accept labels of the action kinds whose rules do not name one
const ACCEPT_LABELS: Partial<Record<ActionKind, string>> = {
  possible_duplicate: "Not a duplicate",
  not_a_consumable: "Accept: keep this record",
  confirm_with_note: "Confirm and accept",
};

/** Return the label of an issue's Accept option. */
export function describeAcceptLabel(rule: IssueActionRule): string {
  return rule.acceptLabel ?? ACCEPT_LABELS[rule.kind] ?? "Accept the value";
}

/** The option the user picked in an action component. */
export type ActionOption = "accept" | "change" | "not_found" | "leave_blank" | "alternative" | "other_value";

/** Everything the user has entered for the selected issue (or the selected field). */
export interface ActionState {
  option: ActionOption | null;
  alternativeIndex: number | null;
  value: string;
  valueProblem: string | null;
  note: string;
  reason: string;
  hasCheckedDocuments: boolean;
}

/** Return a fresh, empty action state. */
export function makeEmptyActionState(): ActionState {
  return {
    option: null,
    alternativeIndex: null,
    value: "",
    valueProblem: null,
    note: "",
    reason: "",
    hasCheckedDocuments: false,
  };
}

/** Remove `change_id` from each change type of a union separately (keeps the `type` link). */
type WithoutChangeId<T> = T extends unknown ? Omit<T, "change_id"> : never;

/** A change as the screen builds it (any §6 type); the change ID is added when it is sent. */
export type NewChange = WithoutChangeId<Change>;

/** What "Save and next issue" does: send a change, or just move on (nothing to save). */
export type IssueChoice = { kind: "change"; change: NewChange } | { kind: "move_on" };

/** The result of checking the user's input: the choice, or why Save is not possible yet. */
export interface ChoiceResult {
  choice: IssueChoice | null;
  hint: string | null;
}

/** What buildChoice needs besides the user's input. */
export interface ChoiceContext {
  issue: IssueSummary | null;
  kind: ActionKind | null;
  recordId: string | null;
  field: RunField | null;
  isSourceViewed: boolean;
}

/** Return a choice that is not ready yet, with the reason. */
function waitFor(hint: string): ChoiceResult {
  return { choice: null, hint };
}

/** Return a set_value change for the field, or why it cannot be built yet. */
function buildSetValue(context: ChoiceContext, state: ActionState, value: string | null, reason: string | null): ChoiceResult {
  if (context.recordId === null || context.field === null) {
    return waitFor("This issue has no field to change.");
  }
  // A new value must be entered and pass the field's checks ("mark not found" sends null)
  if (value !== null && value.length === 0) {
    return waitFor("Enter a value.");
  }
  if (value !== null && state.valueProblem !== null) {
    return waitFor(state.valueProblem);
  }
  const change: NewChange = { type: "set_value", record_id: context.recordId, field: context.field.key, value, reason };
  return { choice: { kind: "change", change }, hint: null };
}

/**
 * Return true when the user must confirm by hand that they checked the documents: a run issue
 * that needs individual review but cites no source passage the viewer could open.
 */
export function needsDocumentsCheck(issue: IssueSummary, isRunIssue: boolean): boolean {
  return isRunIssue && issue.individual_review && issue.sources.length === 0;
}

/** Return an accept_warning change, or why it cannot be accepted yet. */
function buildAccept(context: ChoiceContext, state: ActionState): ChoiceResult {
  const issue = context.issue;
  if (issue === null || issue.severity !== "warning") {
    return waitFor("Only warnings can be accepted. Choose another action.");
  }
  // The source must be opened first; a run issue without sources is confirmed by hand instead
  const isManualCheck = needsDocumentsCheck(issue, context.recordId === null);
  const isSourceViewed = isManualCheck ? state.hasCheckedDocuments : context.isSourceViewed;
  if (issue.individual_review && !isSourceViewed) {
    return waitFor(isManualCheck ? "Confirm you checked the documents before accepting." : "Open the source before accepting this warning.");
  }
  // The catalogue says which warnings need a note saying what the user did
  const note = state.note.trim();
  if (issue.note_required && note.length === 0) {
    return waitFor("Add a note saying what you did, then accept.");
  }
  const change: NewChange = {
    type: "accept_warning",
    issue_id: issue.issue_id,
    source_viewed: isSourceViewed,
    note: note.length > 0 ? note : null,
  };
  return { choice: { kind: "change", change }, hint: null };
}

/** Return the pick_alternative change for the chosen alternative. */
function buildPickAlternative(context: ChoiceContext, state: ActionState): ChoiceResult {
  if (state.alternativeIndex === null || context.recordId === null || context.field === null) {
    return waitFor("Choose one of the values.");
  }
  const change: NewChange = {
    type: "pick_alternative",
    record_id: context.recordId,
    field: context.field.key,
    alternative_index: state.alternativeIndex,
  };
  return { choice: { kind: "change", change }, hint: null };
}

/** Turn the user's input into a choice for "Save and next issue". */
export function buildChoice(context: ChoiceContext, state: ActionState): ChoiceResult {
  // No issue selected: the user is changing a value that had none, so a reason is required
  if (context.issue === null) {
    if (state.reason.trim().length === 0) return waitFor("Add a reason for the change.");
    return buildSetValue(context, state, state.value.trim(), state.reason.trim());
  }
  if (context.issue.status !== "open") {
    return waitFor("This issue is already closed.");
  }
  // Grey issues with nothing to do just move on
  if (context.kind === "nothing_to_do") {
    return { choice: { kind: "move_on" }, hint: null };
  }
  // Entering a value is the only action of these issues
  if (context.kind === "enter_value") {
    return buildSetValue(context, state, state.value.trim(), null);
  }
  return buildOptionChoice(context, state);
}

/** Turn the picked option (accept, change, not found, ...) into a choice. */
function buildOptionChoice(context: ChoiceContext, state: ActionState): ChoiceResult {
  switch (state.option) {
    case "accept":
      return buildAccept(context, state);
    case "change":
    case "other_value":
      return buildSetValue(context, state, state.value.trim(), null);
    case "not_found":
      return buildSetValue(context, state, null, null);
    case "leave_blank":
      return { choice: { kind: "move_on" }, hint: null };
    case "alternative":
      return buildPickAlternative(context, state);
    default:
      return waitFor("Choose what to do with this issue.");
  }
}
