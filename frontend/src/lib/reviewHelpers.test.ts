// Tests for the Review screen's pure helpers: option ranking, quote highlighting, cell display,
// issue navigation order, the name field, and how an action choice becomes a change (notes and
// source checks). Data is synthetic.
import { describe, expect, it } from "vitest";
import { makeCell, makeIssue, makeLocation, makeRow, makeView, SYNTHETIC_FIELDS } from "../test/reviewFixtures";
import { describeCell } from "./cellDisplay";
import { findQuoteRange, splitIntoSegments } from "./highlight";
import { buildChoice, findActionRule, findShortLabel, makeEmptyActionState, type ChoiceContext } from "./issueActions";
import { rankOptions } from "./optionRanking";
import { countRecordsWithOpenIssue, findNameField, findNeighbourIssue, listOpenIssues } from "./reviewIssues";
import { checkValue } from "./valueCheck";

// Synthetic list values
const OPTIONS = ["Room shelf", "Fridge 2-8", "Freezer minus 20", "Fridge door"];

describe("rankOptions", () => {
  it("typed text keeps matching options only, closest first", () => {
    expect(rankOptions(OPTIONS, "fridge", true)).toEqual(["Fridge 2-8", "Fridge door"]);
    expect(rankOptions(OPTIONS, "door", true)).toEqual(["Fridge door"]);
  });

  it("ignores case, spaces and punctuation when matching", () => {
    expect(rankOptions(OPTIONS, "FRIDGE 2–8", true)[0]).toBe("Fridge 2-8");
  });

  it("a hint orders every option without leaving any out", () => {
    const ranked = rankOptions(OPTIONS, "freezer -20", false);
    expect(ranked[0]).toBe("Freezer minus 20");
    expect(ranked).toHaveLength(OPTIONS.length);
  });

  it("blank text keeps the list order", () => {
    expect(rankOptions(OPTIONS, "  ", true)).toEqual(OPTIONS);
  });
});

describe("findQuoteRange", () => {
  it("finds a quote across line breaks, extra spaces, table bars and case", () => {
    const text = "Row | Use 5  mL |\nof reagent";
    const range = findQuoteRange(text, "use 5 mL of reagent");
    expect(range).not.toBeNull();
    expect(text.slice(range?.start, range?.end)).toBe("Use 5  mL |\nof reagent");
  });

  it("returns null for a quote that is not in the text", () => {
    expect(findQuoteRange("synthetic text", "other words")).toBeNull();
  });

  it("splits text into marked and plain segments", () => {
    expect(splitIntoSegments("abcdef", [{ start: 2, end: 4 }])).toEqual([
      { text: "ab", isMarked: false },
      { text: "cd", isMarked: true },
      { text: "ef", isMarked: false },
    ]);
  });
});

describe("describeCell", () => {
  const storage = SYNTHETIC_FIELDS[1];

  it("shows the API's placeholder for a blank-for-now field", () => {
    const cell = makeCell({ is_placeholder: true, display_value: "SYNTHETIC PLACEHOLDER", color: "grey" });
    expect(describeCell(cell, null)).toEqual({ text: "SYNTHETIC PLACEHOLDER", look: "placeholder", writtenText: null });
  });

  it("shows as written and exported values when they differ", () => {
    const cell = makeCell({ value: "5", written_value: "five" });
    expect(describeCell(cell, null)).toMatchObject({ text: "5", writtenText: "five" });
  });

  it("shows 'choose from list' when a list value was not matched", () => {
    const cell = makeCell({ value: null, written_value: "two to eight", color: "red" });
    expect(describeCell(cell, storage)).toMatchObject({ text: "choose from list", writtenText: "two to eight" });
  });

  it("shows how many values a conflict has, Missing when red, not found otherwise", () => {
    const alternatives = [{ index: 0, value: "a", sources: [] }, { index: 1, value: "b", sources: [] }];
    expect(describeCell(makeCell({ alternatives, color: "red" }), null).text).toBe("2 values");
    expect(describeCell(makeCell({ color: "red" }), null).text).toBe("Missing");
    expect(describeCell(makeCell({ color: "grey" }), null).text).toBe("— (not found)");
  });
});

describe("issue navigation", () => {
  // Record 1: a red issue; record 2 (excluded): a red issue; record 3: a yellow and a grey issue
  const view = makeView([
    makeRow("rec_0001", "One", { storage: { issues: [makeIssue({ issue_id: "iss_a" })] } }),
    makeRow("rec_0002", "Two", { storage: { issues: [makeIssue({ issue_id: "iss_b" })] } }, { exclusion: { by: "t", at: "2026-10-16T09:00:00Z", reason: "r" } }),
    makeRow("rec_0003", "Three", {
      amount: { issues: [makeIssue({ issue_id: "iss_c", severity: "warning" }), makeIssue({ issue_id: "iss_d", severity: "info" })] },
    }),
  ], [makeIssue({ issue_id: "iss_run", severity: "warning" })]);

  it("lists open red and yellow issues of included records, then run issues", () => {
    expect(listOpenIssues(view, new Set()).map((ref) => ref.issue.issue_id)).toEqual(["iss_a", "iss_c", "iss_run"]);
  });

  it("next skips saved issues and wraps around", () => {
    expect(findNeighbourIssue(view, new Set(["iss_c"]), "iss_a", 1)?.issue.issue_id).toBe("iss_run");
    expect(findNeighbourIssue(view, new Set(), "iss_run", 1)?.issue.issue_id).toBe("iss_a");
    expect(findNeighbourIssue(view, new Set(), "iss_a", -1)?.issue.issue_id).toBe("iss_run");
  });

  it("the name field is the field flagged is_record_name, wherever it is in the list", () => {
    expect(findNameField(SYNTHETIC_FIELDS)).toBe("item_name");
    const flaggedLast = SYNTHETIC_FIELDS.map((field) => ({ ...field, is_record_name: field.key === "amount" }));
    expect(findNameField(flaggedLast)).toBe("amount");
    expect(findNameField(SYNTHETIC_FIELDS.map((field) => ({ ...field, is_record_name: false })))).toBeNull();
  });
});

describe("buildChoice", () => {
  const storage = SYNTHETIC_FIELDS[1];
  const base: ChoiceContext = { issue: makeIssue(), kind: "enter_value", recordId: "rec_0001", field: storage, isSourceViewed: false, suggestion: null };

  it("an entered value becomes set_value without a reason", () => {
    const state = { ...makeEmptyActionState(), value: "Fridge door" };
    expect(buildChoice(base, state).choice).toEqual({
      kind: "change",
      change: { type: "set_value", record_id: "rec_0001", field: "storage", value: "Fridge door", reason: null },
    });
  });

  it("a value without an issue needs a reason", () => {
    const state = { ...makeEmptyActionState(), value: "Fridge door" };
    expect(buildChoice({ ...base, issue: null, kind: null }, state).hint).toBe("Add a reason for the change.");
    const withReason = buildChoice({ ...base, issue: null, kind: null }, { ...state, reason: "typo" }).choice;
    expect(withReason).toMatchObject({ change: { reason: "typo" } });
  });

  it("an individual-review accept waits for the source to be opened", () => {
    const issue = makeIssue({ severity: "warning", individual_review: true, issue_id: "iss_w" });
    const state = { ...makeEmptyActionState(), option: "accept" as const };
    const context = { ...base, issue, kind: "review_source" as const };
    expect(buildChoice(context, state).choice).toBeNull();
    expect(buildChoice({ ...context, isSourceViewed: true }, state).choice).toEqual({
      kind: "change",
      change: { type: "accept_warning", issue_id: "iss_w", source_viewed: true, note: null },
    });
  });

  it("a note is required when the issue says note_required, whatever its action kind", () => {
    const state = { ...makeEmptyActionState(), option: "accept" as const };
    const noteless = makeIssue({ severity: "warning", issue_id: "iss_n", note_required: false });
    expect(buildChoice({ ...base, issue: noteless, kind: "confirm_with_note" }, state).choice).toMatchObject({ change: { note: null } });
    const noted = makeIssue({ severity: "warning", issue_id: "iss_m", note_required: true });
    const context = { ...base, issue: noted, kind: "accept_or_change" as const };
    expect(buildChoice(context, state).hint).toBe("Add a note saying what you did, then accept.");
    expect(buildChoice(context, { ...state, note: "Checked the method." }).choice).toMatchObject({ change: { note: "Checked the method." } });
  });

  it("a run issue with sources needs them opened; one without sources needs the documents check", () => {
    const state = { ...makeEmptyActionState(), option: "accept" as const, note: "Checked." };
    const withSources = makeIssue({ severity: "warning", individual_review: true, issue_id: "iss_r1", sources: [makeLocation("doc01-c002")] });
    const runContext = { ...base, recordId: null, field: null, issue: withSources, kind: "confirm_with_note" as const };
    // Ticking the box does not replace opening the cited source
    expect(buildChoice(runContext, { ...state, hasCheckedDocuments: true }).hint).toBe("Open the source before accepting this warning.");
    expect(buildChoice({ ...runContext, isSourceViewed: true }, state).choice).toMatchObject({ change: { source_viewed: true } });
    const noSources = makeIssue({ severity: "warning", individual_review: true, issue_id: "iss_r2" });
    expect(buildChoice({ ...runContext, issue: noSources }, state).hint).toBe("Confirm you checked the documents before accepting.");
    expect(buildChoice({ ...runContext, issue: noSources }, { ...state, hasCheckedDocuments: true }).choice).toMatchObject({ change: { source_viewed: true } });
  });

  it("mark not found sends a null value, a conflict pick sends the alternative index", () => {
    const issue = makeIssue({ severity: "warning" });
    expect(buildChoice({ ...base, issue, kind: "review_source" }, { ...makeEmptyActionState(), option: "not_found" }).choice).toMatchObject({ change: { value: null } });
    const picked = buildChoice({ ...base, kind: "pick_alternative" }, { ...makeEmptyActionState(), option: "alternative", alternativeIndex: 1 });
    expect(picked.choice).toEqual({ kind: "change", change: { type: "pick_alternative", record_id: "rec_0001", field: "storage", alternative_index: 1 } });
  });

  it("using the suggestion becomes use_suggestion, and needs a suggestion", () => {
    const suggestion = { value: "Fridge door", source: "matching" as const, reason: "Same place", rule_id: null };
    const state = { ...makeEmptyActionState(), option: "use_suggestion" as const };
    expect(buildChoice({ ...base, suggestion }, state).choice).toEqual({
      kind: "change",
      change: { type: "use_suggestion", record_id: "rec_0001", field: "storage" },
    });
    expect(buildChoice(base, state).choice).toBeNull();
    expect(buildChoice(base, state).hint).toBe("There is no suggestion to use.");
  });

  it("a typed value still wins when the suggestion was not picked", () => {
    const suggestion = { value: "Fridge door", source: "matching" as const, reason: "Same place", rule_id: null };
    const state = { ...makeEmptyActionState(), value: "Room shelf" };
    expect(buildChoice({ ...base, suggestion }, state).choice).toMatchObject({ change: { type: "set_value", value: "Room shelf" } });
  });

  it("a reviewer choice becomes set_value of the chosen list value", () => {
    const context = { ...base, kind: "choose_value" as const, issue: makeIssue({ severity: "warning", choices: ["Fridge 2-8", "Room shelf"] }) };
    expect(buildChoice(context, makeEmptyActionState()).hint).toBe("Choose one of the values.");
    const chosen = { ...makeEmptyActionState(), option: "choice" as const, value: "Room shelf" };
    expect(buildChoice(context, chosen).choice).toMatchObject({ change: { type: "set_value", field: "storage", value: "Room shelf", reason: null } });
  });

  it("grey issues with nothing to do just move on", () => {
    expect(buildChoice({ ...base, issue: makeIssue({ severity: "info" }), kind: "nothing_to_do" }, makeEmptyActionState()).choice).toEqual({ kind: "move_on" });
  });
});

describe("describeCell suggestions", () => {
  const suggestion = { value: "Fridge door", source: "naming" as const, reason: "Rule", rule_id: "R-1" };

  it("a cell with no value and a suggestion shows it as suggested", () => {
    const display = describeCell(makeCell({ suggestion }), SYNTHETIC_FIELDS[1]);
    expect(display).toMatchObject({ text: "Fridge door", look: "suggestion" });
  });

  it("a cell with a value never shows the suggestion", () => {
    const display = describeCell(makeCell({ value: "Room shelf", display_value: "Room shelf", suggestion }), SYNTHETIC_FIELDS[1]);
    expect(display).toMatchObject({ text: "Room shelf", look: "value" });
  });

  it("a blank-for-now cell stays an empty placeholder", () => {
    const display = describeCell(makeCell({ is_placeholder: true, suggestion }), SYNTHETIC_FIELDS[3]);
    expect(display).toMatchObject({ text: "", look: "placeholder" });
  });
});

describe("issue codes of the redesign", () => {
  const NEW_CODES = [
    "VALUE_UNCLEAR",
    "NAME_NOT_SET",
    "REVIEWER_CHOICE_NEEDED",
    "NOT_A_CONCENTRATION",
    "DERIVED_VALUE_MISSING",
    "DERIVED_VALUE_MISMATCH",
    "CONFLICT_CLOSED",
    "PLAUSIBILITY_CHECK",
    "VALUE_INCOMPLETE",
    "MATCHING_SKIPPED",
    "NAMING_SKIPPED",
    "PLAUSIBILITY_SKIPPED",
  ];

  it.each(NEW_CODES)("%s has its own label", (code) => {
    expect(findShortLabel(code)).not.toBeNull();
  });

  it("OR_EQUIVALENT is gone: it falls back by severity like any unknown code", () => {
    expect(findShortLabel("OR_EQUIVALENT")).toBeNull();
    expect(findActionRule(makeIssue({ code: "OR_EQUIVALENT", severity: "warning" }), true).shortLabel).toBe("Check");
  });

  it("only NOT_IN_LOOKUP and NAME_NOT_SET offer the suggestion", () => {
    const offering = NEW_CODES.concat(["NOT_IN_LOOKUP", "REQUIRED_MISSING"]).filter(
      (code) => findActionRule(makeIssue({ code }), true).canUseSuggestion === true,
    );
    expect(offering.sort()).toEqual(["NAME_NOT_SET", "NOT_IN_LOOKUP"]);
  });

  it("the reviewer-choice issue has its own action and the mismatch needs the confirm view", () => {
    expect(findActionRule(makeIssue({ code: "REVIEWER_CHOICE_NEEDED" }), true).kind).toBe("choose_value");
    expect(findActionRule(makeIssue({ code: "DERIVED_VALUE_MISMATCH" }), true).kind).toBe("confirm_with_note");
  });
});

describe("system-set cells", () => {
  it("a blank system value shows nothing, not '(not found)'", () => {
    const cell = makeCell({ origin: "system", extraction_status: null });
    expect(describeCell(cell, SYNTHETIC_FIELDS[0])).toMatchObject({ text: "", look: "placeholder" });
  });
});

describe("countRecordsWithOpenIssue", () => {
  const error = makeIssue({ issue_id: "iss_e", severity: "error" });
  const warning = makeIssue({ issue_id: "iss_w", severity: "warning" });
  const rows = [
    makeRow("rec_0001", "A", { storage: { issues: [error, makeIssue({ issue_id: "iss_e2", severity: "error" })] } }),
    makeRow("rec_0002", "B", { storage: { issues: [warning] }, amount: { issues: [{ ...warning, issue_id: "iss_w2" }] } }),
    makeRow("rec_0003", "C", { storage: { issues: [error, warning] } }),
    makeRow("rec_0004", "D", { storage: { issues: [{ ...error, status: "resolved" }] } }),
    makeRow("rec_0005", "E", { storage: { issues: [error] } }, { exclusion: { reason: "synthetic", by: "u", at: "2026-01-01T00:00:00Z" } as never }),
  ];

  it("counts each record once, however many issues it has", () => {
    expect(countRecordsWithOpenIssue(rows, "error")).toBe(2);
    expect(countRecordsWithOpenIssue(rows, "warning")).toBe(2);
  });
});

describe("checkValue", () => {
  it("checks list values, length and numbers from the field rules", () => {
    expect(checkValue(SYNTHETIC_FIELDS[1], "Fridge")).toBe("Pick a value from the Storage list.");
    expect(checkValue(SYNTHETIC_FIELDS[2], "2.5")).toBeNull();
    expect(checkValue(SYNTHETIC_FIELDS[2], "about 2")).toBe("Amount must be a number, such as 2.5.");
    expect(checkValue(SYNTHETIC_FIELDS[2], "12345678901")).toContain("at most 10 characters");
  });
});
