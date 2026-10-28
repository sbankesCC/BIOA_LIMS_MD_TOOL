// Tests for the Review screen: grid columns and cells, source viewer, banner dismissal,
// Save and next, re-check on moving to another record, and individual-review accepts.
// All data is synthetic; the API is a recording fetch mock behind the client context.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReviewView } from "../api/types";
import { makeRunDetail, renderApp } from "../test/helpers";
import {
  makeFieldList,
  makeIssue,
  makeLocation,
  makeRecordingFetch,
  makeReviewHandler,
  makeRow,
  makeView,
  type RecordedCall,
} from "../test/reviewFixtures";

// The Review screen address of the synthetic run
const REVIEW_PATH = "/runs/run_0001/review";

/** A view with two records: the first has a red lookup issue on Storage, the second a citation warning. */
function makeTwoRecordView(): ReviewView {
  const lookupIssue = makeIssue({ issue_id: "iss_lookup", code: "NOT_IN_LOOKUP", severity: "error", message: "'two to eight' is not in the Storage list." });
  const citationIssue = makeIssue({ issue_id: "iss_citation", code: "CITATION_NOT_VERIFIED", severity: "warning", individual_review: true, message: "Citation could not be found." });
  return makeView([
    makeRow("rec_0001", "Synthetic Buffer A", {
      storage: { value: null, display_value: null, written_value: "two to eight", color: "red", issues: [lookupIssue] },
    }, { action_needed: "fix" }),
    makeRow("rec_0002", "Synthetic Reagent B", {
      amount: {
        color: "yellow",
        issues: [citationIssue],
        sources: [{ location: makeLocation("doc01-c009"), quote: "use 5 mL of reagent" }],
      },
    }, { action_needed: "check" }),
  ]);
}

/** Return the POST calls to a path. */
function findPosts(calls: RecordedCall[], path: string): RecordedCall[] {
  return calls.filter((call) => call.method === "POST" && call.path === path);
}

describe("Review grid", () => {
  it("shows the fields as columns, the name column pinned and one row per record", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView));
    renderApp(REVIEW_PATH, fetchMock);
    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((header) => header.textContent);
    // The name field heads the pinned column and is not repeated among the field columns
    expect(headers).toEqual(["Action needed", "Item Name", "Found in", "Storage", "Amount", "Later Field"]);
    expect(within(table).getAllByRole("columnheader")[1].className).toContain("records-grid__pin--name");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByText("Synthetic Buffer A").closest("td")?.className).toContain("records-grid__pin--name");
    // Action needed is an icon and a word
    expect(within(table).getByText("Fix")).not.toBeNull();
    expect(within(table).getByText("Check")).not.toBeNull();
  });

  it("the pinned name column is the field flagged is_record_name", async () => {
    const fields = makeFieldList().fields.map((field) => ({ ...field, is_record_name: field.key === "storage" }));
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView, (_method, path) =>
      path === "/runs/run_0001/fields" ? { status: 200, body: { ...makeFieldList(), fields } } : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    const table = await screen.findByRole("table");
    const headers = within(table).getAllByRole("columnheader").map((header) => header.textContent);
    expect(headers).toEqual(["Action needed", "Storage", "Found in", "Item Name", "Amount", "Later Field"]);
    expect(within(table).getAllByRole("columnheader")[1].className).toContain("records-grid__pin--name");
  });

  it("shows the placeholder of a blank-for-now field as read-only text", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView));
    renderApp(REVIEW_PATH, fetchMock);
    const placeholders = await screen.findAllByText("SYNTHETIC PLACEHOLDER");
    expect(placeholders).toHaveLength(2);
    expect(placeholders[0].closest("button")).toBeNull();
  });

  it("shows the value as written next to the exported value when they differ", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView));
    renderApp(REVIEW_PATH, fetchMock);
    const cell = await screen.findByRole("button", { name: /Storage: choose from list, written as two to eight, needs a fix/ });
    expect(cell.textContent).toContain("“two to eight”");
    expect(cell.textContent).toContain("→");
    expect(cell.textContent).toContain("choose from list");
  });

  it("filters to records that need action and to excluded records", async () => {
    const view = makeTwoRecordView();
    view.rows.push(makeRow("rec_0003", "Synthetic Plate C", {}, { action_needed: "excluded", exclusion: { by: "tester", at: "2026-10-16T09:00:00Z", reason: "synthetic reason" } }));
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    await screen.findByText("Synthetic Plate C");
    expect(screen.getByText(/Excluded by tester: synthetic reason/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Needs action/ }));
    expect(screen.queryByText("Synthetic Plate C")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Excluded/ }));
    expect(screen.queryByText("Synthetic Buffer A")).toBeNull();
    expect(screen.getByText("Synthetic Plate C")).not.toBeNull();
  });
});

describe("Source viewer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("highlights the quoted passage of a text chunk", async () => {
    const view = makeTwoRecordView();
    view.rows[1].found_in = [makeLocation("doc01-c009")];
    const chunk = { chunk_id: "doc01-c009", kind: "paragraph", text: "Before use,  USE 5 mL of\nreagent at room temperature.", location: makeLocation("doc01-c009") };
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) => (path === "/runs/run_0001/chunks/doc01-c009" ? { status: 200, body: chunk } : null)));
    renderApp(REVIEW_PATH, fetchMock);
    const links = await screen.findAllByRole("button", { name: /synthetic_method\.docx · 5\.1 Materials/ });
    fireEvent.click(links[1]);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByTestId("source-text");
    const marks = dialog.querySelectorAll("mark");
    expect(marks).toHaveLength(1);
    expect(marks[0].textContent).toBe("USE 5 mL of\nreagent");
  });

  it("shows the page image of a scanned chunk", async () => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic-page"), revokeObjectURL: vi.fn() }));
    const view = makeTwoRecordView();
    view.rows[0].found_in = [makeLocation("doc02-p02", { file_name: "synthetic_scan.pdf", section: null, page: 2, is_scanned: true })];
    const chunk = { chunk_id: "doc02-p02", kind: "page_image", text: null, location: view.rows[0].found_in[0] };
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) => {
      if (path === "/runs/run_0001/chunks/doc02-p02") return { status: 200, body: chunk };
      if (path === "/runs/run_0001/chunks/doc02-p02/image") return new Response(new Blob(["png"], { type: "image/png" }), { status: 200, headers: { "Content-Type": "image/png" } });
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: /synthetic_scan\.pdf · p\. 2/ }));
    const image = await screen.findByRole("img", { name: "Scanned page 2 of synthetic_scan.pdf" });
    expect(image.getAttribute("src")).toBe("blob:synthetic-page");
    expect(calls.some((call) => call.path === "/runs/run_0001/chunks/doc02-p02/image")).toBe(true);
  });
});

describe("Run banner", () => {
  const runIssue = makeIssue({ issue_id: "iss_run", code: "SCANNED_PAGES", severity: "warning", message: "synthetic_scan.pdf has scanned pages." });

  it("stays dismissed for the run after the screen opens again", async () => {
    const view = makeView(makeTwoRecordView().rows, [runIssue]);
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view));
    const first = renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText("synthetic_scan.pdf has scanned pages.")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss run messages" }));
    expect(screen.queryByText("synthetic_scan.pdf has scanned pages.")).toBeNull();
    first.unmount();
    // Open the screen again: the dismissal is remembered for this run
    renderApp(REVIEW_PATH, fetchMock);
    await screen.findByText("Synthetic Buffer A");
    expect(screen.queryByText("synthetic_scan.pdf has scanned pages.")).toBeNull();
  });

  it("shows again for another run", async () => {
    window.localStorage.setItem("consumable-type-extractor.banner-dismissed.run_0002", JSON.stringify(["iss_run"]));
    const view = makeView(makeTwoRecordView().rows, [runIssue]);
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText("synthetic_scan.pdf has scanned pages.")).not.toBeNull();
  });
});

describe("Resolution panel", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  /** Open the panel on the Storage cell of the first record. */
  async function openStorageIssue() {
    fireEvent.click(await screen.findByRole("button", { name: /Storage: choose from list/ }));
    return screen.findByRole("complementary", { name: "Resolution panel" });
  }

  it("Save and next posts a set_value change with a new change ID", async () => {
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openStorageIssue();
    expect(within(panel).getByText("Issue 1 of 2 open")).not.toBeNull();
    // Pick the closest list value (the hint is the value as written)
    const box = within(panel).getByRole("combobox");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "fridge 2" } });
    const options = within(panel).getAllByRole("option").map((option) => option.textContent);
    expect(options[0]).toBe("Fridge 2-8");
    fireEvent.mouseDown(within(panel).getByRole("option", { name: "Fridge 2-8" }));
    fireEvent.click(within(panel).getByRole("button", { name: "Save and next issue" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/changes")).toHaveLength(1));
    const body = findPosts(calls, "/runs/run_0001/changes")[0].body as { user: string; timestamp: string; changes: Record<string, unknown>[] };
    expect(body.changes).toHaveLength(1);
    expect(body.changes[0]).toMatchObject({ type: "set_value", record_id: "rec_0001", field: "storage", value: "Fridge 2-8", reason: null });
    expect(String(body.changes[0].change_id)).toMatch(/^chg_[0-9a-f]{32}$/);
    expect(Number.isNaN(Date.parse(body.timestamp))).toBe(false);
  });

  it("moving to another record re-checks the run and reloads the view", async () => {
    let isRechecked = false;
    const afterView = makeTwoRecordView();
    afterView.rows[0].cells[1] = { ...afterView.rows[0].cells[1], value: "Fridge 2-8", display_value: "Fridge 2-8", written_value: null, color: "none", issues: [] };
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => (isRechecked ? afterView : makeTwoRecordView()), (method, path) => {
      if (method === "POST" && path === "/runs/run_0001/recheck") isRechecked = true;
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openStorageIssue();
    const box = within(panel).getByRole("combobox");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "Fridge 2-8" } });
    fireEvent.mouseDown(within(panel).getByRole("option", { name: "Fridge 2-8" }));
    fireEvent.click(within(panel).getByRole("button", { name: "Save and next issue" }));
    // The next issue is on the second record, so the run is re-checked and read again
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(1));
    expect(await within(panel).findByRole("heading", { name: "Synthetic Reagent B" })).not.toBeNull();
    await waitFor(() => expect(screen.queryByRole("button", { name: /Storage: choose from list/ })).toBeNull());
    const viewReads = calls.filter((call) => call.method === "GET" && call.path === "/runs/run_0001/records");
    expect(viewReads.length).toBeGreaterThanOrEqual(2);
  });

  it("does not re-check while the user stays on the same record", async () => {
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView));
    renderApp(REVIEW_PATH, fetchMock);
    await openStorageIssue();
    fireEvent.click(screen.getByRole("button", { name: /Amount: 5$/ }));
    await screen.findByText(/Amount · Change value/);
    expect(findPosts(calls, "/runs/run_0001/recheck")).toHaveLength(0);
  });

  it("an individual-review accept needs the source opened, then sends source_viewed", async () => {
    const chunk = { chunk_id: "doc01-c009", kind: "paragraph", text: "use 5 mL of reagent", location: makeLocation("doc01-c009") };
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView, (_method, path) => (path === "/runs/run_0001/chunks/doc01-c009" ? { status: 200, body: chunk } : null)));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: /Amount: 5, check/ }));
    const panel = await screen.findByRole("complementary", { name: "Resolution panel" });
    const accept = within(panel).getByRole("radio", { name: /Accept the value/ }) as HTMLInputElement;
    expect(accept.disabled).toBe(true);
    // Open the source, close it, then accept
    fireEvent.click(within(panel).getByRole("button", { name: /View source/ }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close source" }));
    expect(accept.disabled).toBe(false);
    fireEvent.click(accept);
    fireEvent.click(within(panel).getByRole("button", { name: "Save and next issue" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/changes")).toHaveLength(1));
    const body = findPosts(calls, "/runs/run_0001/changes")[0].body as { changes: Record<string, unknown>[] };
    expect(body.changes[0]).toMatchObject({ type: "accept_warning", issue_id: "iss_citation", source_viewed: true, note: null });
  });

  it("a warning with note_required needs a note before it can be accepted", async () => {
    const view = makeTwoRecordView();
    view.rows[1].record_issues = [makeIssue({ issue_id: "iss_split", code: "SHOULD_BE_SPLIT", severity: "warning", individual_review: true, note_required: true, message: "May cover several consumables." })];
    const chunk = { chunk_id: "rec_0002-c1", kind: "paragraph", text: "synthetic text", location: makeLocation("rec_0002-c1") };
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) => (path === "/runs/run_0001/chunks/rec_0002-c1" ? { status: 200, body: chunk } : null)));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: /Amount: 5, check/ }));
    const panel = await screen.findByRole("complementary", { name: "Resolution panel" });
    fireEvent.click(within(panel).getByRole("button", { name: /Record\s*Should be split/ }));
    fireEvent.click(await within(panel).findByRole("button", { name: /View source/ }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "Close source" }));
    fireEvent.click(within(panel).getByRole("radio", { name: /Confirm and accept/ }));
    const save = within(panel).getByRole("button", { name: "Save and next issue" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    expect(within(panel).getByText("Add a note saying what you did, then accept.")).not.toBeNull();
    fireEvent.change(within(panel).getByLabelText(/Note: what you did/), { target: { value: "Checked: one consumable." } });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/changes")).toHaveLength(1));
    const body = findPosts(calls, "/runs/run_0001/changes")[0].body as { changes: Record<string, unknown>[] };
    expect(body.changes[0]).toMatchObject({ type: "accept_warning", issue_id: "iss_split", source_viewed: true, note: "Checked: one consumable." });
  });

  it("shows the API's message when a change is refused", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView, (method, path) =>
      method === "POST" && path === "/runs/run_0001/changes"
        ? { status: 400, body: { error: { code: "CHANGE_INVALID", message: "'Fridge 2-8' is not an allowed value for Storage. Pick a value from the list.", details: {} } } }
        : null,
    ));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openStorageIssue();
    const box = within(panel).getByRole("combobox");
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "Fridge 2-8" } });
    fireEvent.mouseDown(within(panel).getByRole("option", { name: "Fridge 2-8" }));
    fireEvent.click(within(panel).getByRole("button", { name: "Save and next issue" }));
    const alert = await within(panel).findByRole("alert");
    expect(alert.textContent).toContain("is not an allowed value for Storage");
  });
});

describe("Run issue sources", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  /** A run issue that needs individual review and a note, with these cited locations. */
  function makeMissedIssue(sources: ReturnType<typeof makeLocation>[]) {
    return makeIssue({
      issue_id: "iss_missed",
      code: "MISSED_CANDIDATES_UNRESOLVED",
      severity: "warning",
      individual_review: true,
      note_required: true,
      message: "These items may be missing from the results: Synthetic Wash Strip.",
      sources,
    });
  }

  /** Open the run issue from the banner and return the panel. */
  async function openRunIssue() {
    const banner = await screen.findByRole("region", { name: "Run messages" });
    fireEvent.click(within(banner).getByRole("button", { name: /Review/ }));
    return screen.findByRole("complementary", { name: "Resolution panel" });
  }

  it("opens the issue's cited passage in the source viewer and accepts only after that", async () => {
    const location = makeLocation("doc01-c004", { section: "6.2 Plate washing" });
    const view = makeView(makeTwoRecordView().rows, [makeMissedIssue([location])]);
    const chunk = { chunk_id: "doc01-c004", kind: "paragraph", text: "Wash with Synthetic Wash Strip.", location };
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(() => view, (_method, path) => (path === "/runs/run_0001/chunks/doc01-c004" ? { status: 200, body: chunk } : null)));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openRunIssue();
    // No manual "checked the documents" box: the source itself must be opened
    expect(within(panel).queryByRole("checkbox")).toBeNull();
    const accept = within(panel).getByRole("radio", { name: /Confirm and accept/ }) as HTMLInputElement;
    expect(accept.disabled).toBe(true);
    fireEvent.click(within(panel).getByRole("button", { name: /View source/ }));
    const viewer = await screen.findByRole("dialog");
    expect(await within(viewer).findByText("Wash with Synthetic Wash Strip.")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close source" }));
    expect(accept.disabled).toBe(false);
    fireEvent.click(accept);
    fireEvent.change(within(panel).getByLabelText(/Note: what you did/), { target: { value: "Added it outside the tool." } });
    fireEvent.click(within(panel).getByRole("button", { name: "Save and next issue" }));
    await waitFor(() => expect(findPosts(calls, "/runs/run_0001/changes")).toHaveLength(1));
    const body = findPosts(calls, "/runs/run_0001/changes")[0].body as { changes: Record<string, unknown>[] };
    expect(body.changes[0]).toMatchObject({ type: "accept_warning", issue_id: "iss_missed", source_viewed: true, note: "Added it outside the tool." });
  });

  it("a run issue without sources says so and asks the user to confirm they checked the documents", async () => {
    const view = makeView(makeTwoRecordView().rows, [makeMissedIssue([])]);
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    const panel = await openRunIssue();
    expect(within(panel).getByText(/No source passage was recorded for these items/)).not.toBeNull();
    expect(within(panel).queryByRole("button", { name: /View source/ })).toBeNull();
    const accept = within(panel).getByRole("radio", { name: /Confirm and accept/ }) as HTMLInputElement;
    expect(accept.disabled).toBe(true);
    fireEvent.click(within(panel).getByRole("checkbox", { name: "I checked the documents for these items" }));
    expect(accept.disabled).toBe(false);
  });
});

describe("Review header", () => {
  it("renames the run through PATCH /runs/{run_id}", async () => {
    const { fetchMock, calls } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView, (method, path, body) => {
      if (method === "PATCH" && path === "/runs/run_0001") {
        return { status: 200, body: makeRunDetail({ status: "in_review", current_step: null, name: (body as { name: string }).name }) };
      }
      return null;
    }));
    renderApp(REVIEW_PATH, fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Rename run" }));
    fireEvent.change(screen.getByLabelText("Run name"), { target: { value: "  Renamed synthetic run " } });
    fireEvent.click(screen.getByRole("button", { name: "Save name" }));
    expect(await screen.findByRole("heading", { name: "Renamed synthetic run" })).not.toBeNull();
    expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ name: "Renamed synthetic run" });
  });
});

describe("Review grid wording (mockup pass)", () => {
  it("shows how many records are shown under the grid, and the filter changes the count", async () => {
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(makeTwoRecordView));
    renderApp(REVIEW_PATH, fetchMock);
    expect(await screen.findByText(/^Showing 2 of 2 records · Scroll for more records and columns/)).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /^Excluded/ }));
    expect(await screen.findByText(/^Showing 0 of 2 records/)).not.toBeNull();
  });

  it("Found in shows the last heading of a section path, with the full path as its title", async () => {
    const view = makeTwoRecordView();
    view.rows[0].found_in = [makeLocation("doc01-c001", { section: "Synthetic Method > 6 Materials > 6.2 Reagents" })];
    const { fetchMock } = makeRecordingFetch(makeReviewHandler(() => view));
    renderApp(REVIEW_PATH, fetchMock);
    const link = await screen.findByText("synthetic_method.docx · 6.2 Reagents");
    expect(link.closest("button")?.title).toBe("synthetic_method.docx · Synthetic Method > 6 Materials > 6.2 Reagents");
  });
});
