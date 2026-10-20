// Tests for the possible-duplicate comparison in the resolution panel, and the admin helpers
// it shares a milestone with (version changes text, next version name, download file name).
// All data is synthetic: candidate names and reasons are made up for the test.
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { readFileName } from "../../api/admin";
import type { DataVersionInfo } from "../../api/types";
import { describeApplyBlock, describeVersionChanges, findNextVersionName, listAppliedVersions } from "../../lib/adminVersions";
import { describeMatch, listRecordValues, showAttribute } from "../../lib/duplicateCandidates";
import { makeRunDetail, renderApp } from "../../test/helpers";
import { SYNTHETIC_FIELDS, makeIssue, makeRecordingFetch, makeReviewHandler, makeRow, makeView } from "../../test/reviewFixtures";

// A possible-duplicate warning on the name field, with its existing types as the review view gives them
const DUPLICATE_CANDIDATES = [
  { candidate_id: "ref_0001", name: "synthetic buffer a", match: "normalized", reason: null, description: "Synthetic existing description", consumable_class: "Synthetic class", active_flag: "Y" },
  { candidate_id: "ref_0002", name: "Synthetic Buffer A2", match: "unsure", reason: "Synthetic reason: names differ by one character.", description: null, consumable_class: null, active_flag: null },
];
const DUPLICATE_ISSUE = makeIssue({ issue_id: "iss_dup", code: "POSSIBLE_DUPLICATE", severity: "warning", message: "May already exist in LabVantage.", duplicate_candidates: DUPLICATE_CANDIDATES });

/** A view with one record whose name has the possible-duplicate warning (or `issue`). */
function makeDuplicateView(issue = DUPLICATE_ISSUE) {
  return makeView([makeRow("rec_0001", "Synthetic Buffer A", { item_name: { color: "yellow", issues: [issue] } }, { action_needed: "check" })]);
}

/** Answer the run with a reference data version. */
function answerRun(_method: string, path: string) {
  if (path === "/runs/run_0001") {
    return { status: 200, body: makeRunDetail({ status: "in_review", current_step: null, reference_data_version: "v-synthetic-ref" }) };
  }
  return null;
}

describe("Possible duplicate comparison", () => {
  it("shows this record next to each existing type with its attributes, how it matched and the checker's reason", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => makeDuplicateView(), answerRun));
    renderApp("/runs/run_0001/review", fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: /Item Name: Synthetic Buffer A/ }));
    const panel = await screen.findByRole("complementary", { name: "Resolution panel" });
    const table = await within(panel).findByRole("table", { name: "Side-by-side comparison" });
    // One column for the record, one per existing type
    const headers = within(table).getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(["This record", "Existing type 1", "Existing type 2"]);
    const rows = within(table).getAllByRole("row").slice(1).map((row) => Array.from(row.children).map((cell) => cell.textContent));
    expect(rows[0]).toEqual(["Name", "Synthetic Buffer A", "synthetic buffer a", "Synthetic Buffer A2"]);
    expect(rows[1][2]).toBe("LabVantage (reference data v-synthetic-ref)");
    // Attributes from the reference data; "—" where it has none (never made up)
    expect(rows[2]).toEqual(["Description", "StorageRoom shelfAmount5", "Synthetic existing description", "—"]);
    expect(rows[3]).toEqual(["Class", "Synthetic class", "—"]);
    expect(rows[4]).toEqual(["Active flag", "Y", "—"]);
    expect(rows[5]).toEqual(["Why it matched", "—", "Same name apart from capitals, spaces or °", "The duplicate checker could not tell"]);
    expect(rows[6]).toEqual(["Checker's reason", "—", "—", "Synthetic reason: names differ by one character."]);
    // This record's extracted values sit beside the attributes (no name, no placeholder field)
    const values = within(table).getByLabelText("This record's values");
    expect(within(values).queryByText("Item Name")).toBeNull();
    expect(within(values).queryByText("Later Field")).toBeNull();
    // The actions stay: Not a duplicate (accept); the old "only the name" note is gone
    expect(within(panel).getByRole("radio", { name: /Not a duplicate/ })).not.toBeNull();
    expect(within(panel).queryByText(/Only the name of an existing type is available here/)).toBeNull();
  });

  it("is not shown for an issue without existing types in its details", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => makeDuplicateView(makeIssue({ issue_id: "iss_dup", code: "POSSIBLE_DUPLICATE", severity: "warning", message: "May already exist in LabVantage." }))));
    renderApp("/runs/run_0001/review", fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: /Item Name: Synthetic Buffer A/ }));
    const panel = await screen.findByRole("complementary", { name: "Resolution panel" });
    await within(panel).findByText("May already exist in LabVantage.");
    expect(within(panel).queryByRole("table", { name: "Side-by-side comparison" })).toBeNull();
  });
});

describe("Duplicate and admin helpers", () => {
  it("explains matches, shows missing attributes as a dash and lists only the record's extracted values", () => {
    expect(describeMatch("exact")).toBe("Exactly the same name");
    expect(describeMatch(null)).toBe("—");
    expect(showAttribute(null)).toBe("—");
    expect(showAttribute("Synthetic")).toBe("Synthetic");
    const row = makeRow("rec_0001", "Synthetic Buffer A", { amount: { value: null, display_value: null } });
    expect(listRecordValues(row, SYNTHETIC_FIELDS)).toEqual([{ column: "Storage", value: "Room shelf" }]);
    expect(listRecordValues(null, SYNTHETIC_FIELDS)).toEqual([]);
  });

  it("describes version changes, the next version name and why an upload cannot be applied", () => {
    const base: DataVersionInfo = {
      upload_id: "upl_0001",
      version_id: "v1",
      status: "superseded",
      file_name: "synthetic.xlsx",
      based_on_version: null,
      uploaded_by: "synthetic.admin",
      uploaded_at: "2026-10-16T09:14:00Z",
      applied_by: null,
      applied_at: null,
      summary: { added_values: 1, removed_values: 3, row_count: 2 },
    };
    expect(describeVersionChanges(base, "lookup")).toBe("+1 value, −3");
    expect(describeVersionChanges(base, "reference")).toBe("2 existing types");
    expect(describeVersionChanges({ ...base, summary: {} }, "lookup")).toBe("—");
    const list = { current_version: "v2", versions: [base, { ...base, upload_id: "upl_0002", version_id: "v2" }, { ...base, upload_id: "upl_0003", version_id: null }] };
    expect(findNextVersionName(list)).toBe("v3");
    expect(listAppliedVersions(list).map((version) => version.version_id)).toEqual(["v2", "v1"]);
    const report = { file_name: "x", row_count: 0, passed_checks: [], problems: [], warnings: [] };
    expect(describeApplyBlock(report, base)).toBeNull();
    expect(describeApplyBlock({ ...report, problems: [{ severity: "problem", code: "X", message: "m" }] }, null)).toBe("Fix the 1 problem and upload again to apply these updates");
  });

  it("reads the file name of a download header", () => {
    expect(readFileName('attachment; filename="synthetic v2.xlsx"')).toBe("synthetic v2.xlsx");
    expect(readFileName(null)).toBeNull();
  });
});
