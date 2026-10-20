// Tests for the Admin screens: current version card, upload report (problems block the apply,
// warnings do not), the diff, Apply, Restore, downloads, reference data and 403 handling.
// All data is synthetic (no client lists or values); the API is a recording fetch mock.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DataVersionInfo, DataVersionList, LookupUploadReport, ReferenceUploadReport } from "../api/types";
import { renderApp } from "../test/helpers";
import type { ReviewAnswer } from "../test/reviewFixtures";

/** One recorded request: method, path (without /api) and whether it carried a `file` part. */
interface AdminCall {
  method: string;
  path: string;
  hasFilePart: boolean;
}

/** Make a fetch mock that records each call (a multipart body is checked for its `file` part) and answers through the handler. */
function makeRecordingFetch(handler: (method: string, path: string) => ReviewAnswer) {
  const calls: AdminCall[] = [];
  const fetchMock = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname.replace(/^\/api/, "");
    // Uploads are multipart: note the name of the file part
    const isForm = (request.headers.get("Content-Type") ?? "").startsWith("multipart/form-data");
    const text = isForm ? await request.clone().text() : "";
    calls.push({ method: request.method, path, hasFilePart: text.includes('name="file"') });
    const answer = handler(request.method, path);
    if (answer instanceof Response) return answer;
    return new Response(JSON.stringify(answer.body), { status: answer.status, headers: { "Content-Type": "application/json" } });
  });
  return { fetchMock, calls };
}

/** Return a synthetic version entry, changed by `overrides`. */
function makeVersion(overrides: Partial<DataVersionInfo> = {}): DataVersionInfo {
  return {
    upload_id: "upl_0001",
    version_id: "v1",
    status: "current",
    file_name: "synthetic_lists.xlsx",
    based_on_version: "v0-synthetic",
    uploaded_by: "synthetic.admin",
    uploaded_at: "2026-10-16T09:14:00Z",
    applied_by: "synthetic.admin",
    applied_at: "2026-10-16T09:20:00Z",
    summary: { added_values: 4, removed_values: 0 },
    ...overrides,
  };
}

/** A history with v2 current and v1 superseded. */
function makeHistory(): DataVersionList {
  return {
    current_version: "v2",
    versions: [
      makeVersion({ upload_id: "upl_0001", version_id: "v1", status: "superseded", summary: { added_values: 12, removed_values: 2 } }),
      makeVersion({ upload_id: "upl_0002", version_id: "v2", status: "current", uploaded_by: "synthetic.other" }),
    ],
  };
}

/** Return a synthetic lookup upload report, changed by `overrides`. */
function makeLookupReport(overrides: Partial<LookupUploadReport> = {}): LookupUploadReport {
  return {
    file_name: "synthetic_edit.xlsx",
    current_version: "v2",
    based_on_version: "v2",
    passed_checks: ["Based on the current version (v2)", "All expected sheets and headers present"],
    problems: [],
    warnings: [],
    changes: [
      { sheet: "Synthetic List A", added: ["Alpha one", "Alpha two"], removed: [], is_new_sheet: false, is_removed_sheet: false },
      { sheet: "Synthetic List B", added: [], removed: ["Beta old"], is_new_sheet: false, is_removed_sheet: false },
    ],
    ...overrides,
  };
}

// A problem and a warning as the API reports them
const PROBLEM = { severity: "problem" as const, code: "LEADING_SPACE", sheet: "Synthetic List A", row: 7, message: "“ Alpha two” starts with a space." };
const WARNING = { severity: "warning" as const, code: "VALUE_TOO_LONG", sheet: "Synthetic List B", row: 3, message: "46 characters; the field's limit is 40." };

/** Return an error answer in the API's shape. */
function errorAnswer(status: number, code: string, message: string): ReviewAnswer {
  return { status, body: { error: { code, message, details: {} } } };
}

/** Make an admin API mock: history, upload answer and apply answers, with `extra` tried first. */
function makeAdminHandler(options: { history?: () => DataVersionList; upload?: unknown; extra?: (method: string, path: string) => ReviewAnswer | null } = {}) {
  const history = options.history ?? makeHistory;
  return (method: string, path: string): ReviewAnswer => {
    const answer = options.extra?.(method, path) ?? null;
    if (answer !== null) return answer;
    if (path === "/admin/lookup-lists/versions" || path === "/admin/reference-data/versions") return { status: 200, body: history() };
    if (method === "POST" && (path === "/admin/lookup-lists" || path === "/admin/reference-data")) return { status: 200, body: options.upload };
    if (method === "POST" && path.endsWith("/apply")) return { status: 200, body: makeVersion({ version_id: path.split("/")[3].startsWith("upl_") ? "v3" : path.split("/")[3] }) };
    return errorAnswer(404, "NOT_FOUND", `No mock for ${method} ${path}.`);
  };
}

/** Upload a synthetic file through the hidden file input. */
function uploadFile(name: string) {
  const input = screen.getByLabelText("File to upload") as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["synthetic"], name)] } });
}

/** Return the POST calls to a path. */
function findPosts(calls: AdminCall[], path: string): AdminCall[] {
  return calls.filter((call) => call.method === "POST" && call.path === path);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Admin: lookup lists", () => {
  it("shows the current version card and the history with Current, Superseded and Restore", async () => {
    const { fetchMock } = makeRecordingFetch(makeAdminHandler());
    renderApp("/admin", fetchMock);
    expect(await screen.findByRole("heading", { name: "Current version: v2" })).not.toBeNull();
    expect(screen.getByText(/Uploaded by synthetic\.other/)).not.toBeNull();
    expect(screen.getByRole("button", { name: /Download current workbook/ })).not.toBeNull();
    // The Admin button is filled on the admin screens (mockup 4)
    expect(screen.getByRole("link", { name: "Admin" }).className).toContain("top-bar__admin--active");
    // Newest first; only a superseded version can be restored
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["v2", "v1"]);
    expect(within(rows[0]).getByText("Current")).not.toBeNull();
    expect(within(rows[0]).queryByRole("button", { name: /Restore/ })).toBeNull();
    expect(within(rows[1]).getByText("Superseded")).not.toBeNull();
    expect(within(rows[1]).getByText("+12 values, −2")).not.toBeNull();
    expect(within(rows[1]).getByRole("button", { name: "Restore v1" })).not.toBeNull();
  });

  it("an upload with problems lists them and keeps Apply disabled with the reason", async () => {
    const upload = { report: makeLookupReport({ problems: [PROBLEM], warnings: [WARNING] }), version: null };
    const { fetchMock, calls } = makeRecordingFetch(makeAdminHandler({ upload }));
    renderApp("/admin", fetchMock);
    await screen.findByRole("heading", { name: "Current version: v2" });
    uploadFile("synthetic_edit.xlsx");
    // Problems (red) and warnings (amber) are separate boxes, each with sheet, row and message
    const problems = await screen.findByRole("group", { name: "1 problem to fix before applying" });
    expect(within(problems).getByText("Synthetic List A").tagName).toBe("STRONG");
    expect(problems.textContent).toContain("row 7: “ Alpha two” starts with a space.");
    const warnings = screen.getByRole("group", { name: "1 warning: these do not stop the update" });
    expect(warnings.textContent).toContain("Synthetic List B, row 3: 46 characters; the field's limit is 40.");
    expect(screen.getByText("Based on the current version (v2)")).not.toBeNull();
    // Apply is disabled and says why
    const apply = screen.getByRole("button", { name: "Apply updates as v3" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    expect(screen.getByText("Fix the 1 problem and upload again to apply these updates")).not.toBeNull();
    expect(findPosts(calls, "/admin/lookup-lists").map((call) => call.hasFilePart)).toEqual([true]);
  });

  it("warnings alone do not block: Apply updates posts the pending upload and reloads the history", async () => {
    const pending = makeVersion({ upload_id: "upl_0003", version_id: null, status: "pending" });
    const upload = { report: makeLookupReport({ warnings: [WARNING] }), version: pending };
    const { fetchMock, calls } = makeRecordingFetch(makeAdminHandler({ upload }));
    renderApp("/admin", fetchMock);
    await screen.findByRole("heading", { name: "Current version: v2" });
    uploadFile("synthetic_edit.xlsx");
    const apply = (await screen.findByRole("button", { name: "Apply updates as v3" })) as HTMLButtonElement;
    expect(apply.disabled).toBe(false);
    fireEvent.click(apply);
    expect(await screen.findByText(/Applied as v3\. New runs use it/)).not.toBeNull();
    expect(findPosts(calls, "/admin/lookup-lists/upl_0003/apply")).toHaveLength(1);
    const historyReads = calls.filter((call) => call.path === "/admin/lookup-lists/versions");
    // One read by the Admin link check, one on open, one after the apply
    expect(historyReads.length).toBeGreaterThanOrEqual(3);
  });

  it("shows the changes by list and every added and removed value on request", async () => {
    const upload = { report: makeLookupReport(), version: makeVersion({ upload_id: "upl_0003", version_id: null, status: "pending" }) };
    const { fetchMock } = makeRecordingFetch(makeAdminHandler({ upload }));
    renderApp("/admin", fetchMock);
    await screen.findByRole("heading", { name: "Current version: v2" });
    uploadFile("synthetic_edit.xlsx");
    expect(await screen.findByRole("heading", { name: "Changes from v2" })).not.toBeNull();
    const tables = screen.getAllByRole("table");
    const changeRows = within(tables[0]).getAllByRole("row").slice(1).map((row) => row.textContent);
    expect(changeRows).toEqual(["Synthetic List A20", "Synthetic List B01"]);
    // The full list opens under the table
    fireEvent.click(screen.getByRole("button", { name: "View every added and removed value" }));
    const all = screen.getByLabelText("Every added and removed value");
    expect(all.textContent).toContain("Added: “Alpha one”; “Alpha two”");
    expect(all.textContent).toContain("Removed: “Beta old”");
  });

  it("Restore asks first, then applies the older version by its name", async () => {
    const { fetchMock, calls } = makeRecordingFetch(makeAdminHandler());
    renderApp("/admin", fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Restore v1" }));
    const dialog = screen.getByRole("dialog", { name: "Restore v1?" });
    expect(findPosts(calls, "/admin/lookup-lists/v1/apply")).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore v1" }));
    expect(await screen.findByText(/Restored v1\. New runs use it/)).not.toBeNull();
    expect(findPosts(calls, "/admin/lookup-lists/v1/apply")).toHaveLength(1);
  });

  it("shows the API's message when an apply is refused (stale upload)", async () => {
    const pending = makeVersion({ upload_id: "upl_0003", version_id: null, status: "pending" });
    const stale = errorAnswer(409, "UPLOAD_STALE", "This upload was based on v1, but v2 is now current. Download the current workbook and make your edits again.");
    const extra = (method: string, path: string) => (method === "POST" && path === "/admin/lookup-lists/upl_0003/apply" ? stale : null);
    const { fetchMock } = makeRecordingFetch(makeAdminHandler({ upload: { report: makeLookupReport(), version: pending }, extra }));
    renderApp("/admin", fetchMock);
    await screen.findByRole("heading", { name: "Current version: v2" });
    uploadFile("synthetic_edit.xlsx");
    fireEvent.click(await screen.findByRole("button", { name: "Apply updates as v3" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Download the current workbook and make your edits again.");
  });

  it("downloads the current workbook under the API's file name", async () => {
    const { fetchMock } = makeRecordingFetch(
      makeAdminHandler({
        extra: (_method, path) =>
          path === "/admin/lookup-lists/current"
            ? new Response(new Blob(["synthetic"]), { status: 200, headers: { "Content-Disposition": 'attachment; filename="synthetic_lists v2.xlsx"' } })
            : null,
      }),
    );
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic-file"), revokeObjectURL: vi.fn() }));
    const names: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      names.push(this.download);
    });
    renderApp("/admin", fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: /Download current workbook/ }));
    await waitFor(() => expect(names).toEqual(["synthetic_lists v2.xlsx"]));
  });
});

describe("Admin: reference data", () => {
  it("shows the empty state, uploads to the reference data endpoint and shows the rows read", async () => {
    const report: ReferenceUploadReport = { file_name: "synthetic_types.csv", row_count: 3, passed_checks: ["All mapped columns present"], problems: [], warnings: [WARNING] };
    const pending = makeVersion({ upload_id: "upl_0001", version_id: null, status: "pending", summary: { row_count: 3 } });
    const { fetchMock, calls } = makeRecordingFetch(makeAdminHandler({ history: () => ({ current_version: null, versions: [] }), upload: { report, version: pending } }));
    renderApp("/admin/reference-data", fetchMock);
    expect(await screen.findByRole("heading", { name: "No reference data yet" })).not.toBeNull();
    // Reference data has no download endpoint, so no download button
    expect(screen.queryByRole("button", { name: /Download/ })).toBeNull();
    uploadFile("synthetic_types.csv");
    expect(await screen.findByText("Rows read: 3")).not.toBeNull();
    expect(findPosts(calls, "/admin/reference-data").map((call) => call.hasFilePart)).toEqual([true]);
    fireEvent.click(screen.getByRole("button", { name: "Apply updates as v1" }));
    await waitFor(() => expect(findPosts(calls, "/admin/reference-data/upl_0001/apply")).toHaveLength(1));
  });
});

describe("Admin access", () => {
  const forbidden = errorAnswer(403, "FORBIDDEN", "This needs the admin role. Ask an admin for access.");

  it("a 403 from an admin call shows a plain message and hides the Admin link", async () => {
    const { fetchMock } = makeRecordingFetch(() => forbidden);
    renderApp("/admin", fetchMock);
    expect(await screen.findByRole("heading", { name: "You do not have access to the admin screens" })).not.toBeNull();
    await waitFor(() => expect(screen.queryByRole("link", { name: "Admin" })).toBeNull());
    expect(screen.queryByRole("button", { name: /Download current workbook/ })).toBeNull();
  });

  it("the Admin link stays when the admin check fails for another reason", async () => {
    const { fetchMock, calls } = makeRecordingFetch(() => errorAnswer(503, "SETTING_MISSING", "Set REVIEW_DB, then restart the app."));
    renderApp("/runs", fetchMock);
    await waitFor(() => expect(calls.some((call) => call.path === "/admin/lookup-lists/versions")).toBe(true));
    expect(screen.getByRole("link", { name: "Admin" })).not.toBeNull();
  });

  it("the Admin link is hidden on other screens once the API answers 403", async () => {
    const { fetchMock } = makeRecordingFetch((_method, path) => (path.startsWith("/admin") ? forbidden : { status: 200, body: [] }));
    renderApp("/runs", fetchMock);
    await waitFor(() => expect(screen.queryByRole("link", { name: "Admin" })).toBeNull());
  });
});
