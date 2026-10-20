// Tests for the Start a run screen: file list and type check, name suggestion, the disabled
// button, submitting through the API client (mocked fetch), API errors and recent runs.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildRunForm } from "../api/runs";
import { formatDay } from "../lib/format";
import { makeFetchMock, makeRunDetail, makeRunSummary, renderApp, type MockHandler } from "../test/helpers";

/** Make a synthetic file of a given size in bytes. */
function makeFile(name: string, sizeBytes = 2048): File {
  return new File([new Uint8Array(sizeBytes)], name, { lastModified: 1 });
}

/** Add files through the hidden file input, as "Browse files" does. */
function addFiles(files: File[]) {
  fireEvent.change(screen.getByLabelText("Add files"), { target: { files } });
}

/** An API with no runs yet that starts run_0007 and then reports it processing. */
const startingApi: MockHandler = (method, path) => {
  if (method === "GET" && path === "/runs") return { status: 200, body: [] };
  if (method === "POST" && path === "/runs") return { status: 202, body: { run_id: "run_0007", retry_of: null } };
  if (method === "GET" && path === "/runs/run_0007") {
    return { status: 200, body: makeRunDetail({ run_id: "run_0007", name: "Started run" }) };
  }
  return { status: 404, body: { error: { code: "NOT_FOUND", message: "Not found.", details: {} } } };
};

describe("Start a run screen", () => {
  it("start extraction is disabled until a file is added", () => {
    renderApp("/", makeFetchMock(startingApi));
    const start = screen.getByRole("button", { name: /Start extraction/ }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    addFiles([makeFile("Synthetic_Method_A.pdf")]);
    expect(start.disabled).toBe(false);
  });

  it("added files are listed with their type and size", () => {
    renderApp("/", makeFetchMock(startingApi));
    addFiles([makeFile("Synthetic_Method_A.pdf", 2048), makeFile("Synthetic_Plan.docx", 3 * 1024 * 1024)]);
    const list = screen.getByRole("list", { name: "Files" });
    expect(within(list).getByText("Synthetic_Method_A.pdf")).not.toBeNull();
    expect(within(list).getByText("PDF · 2 KB")).not.toBeNull();
    expect(within(list).getByText("Word · 3.0 MB")).not.toBeNull();
    expect(screen.getByText(/2 files ready/)).not.toBeNull();
  });

  it("a refused file type is shown with a message and not counted", () => {
    renderApp("/", makeFetchMock(startingApi));
    addFiles([makeFile("Synthetic_Email.msg")]);
    expect(screen.getByText("Not added: only Word, PDF and Excel files are accepted")).not.toBeNull();
    const start = screen.getByRole("button", { name: /Start extraction/ }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });

  it("removing a file takes it out of the list", () => {
    renderApp("/", makeFetchMock(startingApi));
    addFiles([makeFile("Synthetic_Method_A.pdf"), makeFile("Synthetic_Sheet.xlsx")]);
    fireEvent.click(screen.getByRole("button", { name: "Remove Synthetic_Method_A.pdf" }));
    expect(screen.queryByText("Synthetic_Method_A.pdf")).toBeNull();
    expect(screen.getByText(/1 file ready/)).not.toBeNull();
  });

  it("the run name is suggested from the first file and today's date", () => {
    renderApp("/", makeFetchMock(startingApi));
    addFiles([makeFile("Synthetic_Method_A.pdf")]);
    const nameInput = screen.getByLabelText("Run name") as HTMLInputElement;
    expect(nameInput.value).toBe(`Synthetic Method A – ${formatDay(new Date())}`);
  });

  it("a typed run name is kept when more files are added", () => {
    renderApp("/", makeFetchMock(startingApi));
    const nameInput = screen.getByLabelText("Run name") as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: "My synthetic run" } });
    addFiles([makeFile("Synthetic_Method_A.pdf")]);
    expect(nameInput.value).toBe("My synthetic run");
  });

  it("submit posts the run through the API client and opens its processing screen", async () => {
    const fetchMock = makeFetchMock(startingApi);
    renderApp("/", fetchMock);
    addFiles([makeFile("Synthetic_Method_A.pdf"), makeFile("Synthetic_Email.msg")]);
    fireEvent.click(screen.getByRole("button", { name: /Start extraction/ }));
    // The new run's screen opens
    expect(await screen.findByRole("heading", { name: "Started run" })).not.toBeNull();
    // Exactly one POST /runs was sent
    const posts = fetchMock.mock.calls.filter(([request]) => request.method === "POST");
    expect(posts).toHaveLength(1);
    expect(new URL(posts[0][0].url).pathname).toBe("/api/runs");
  });

  it("a missing setting (503) shows the message naming the setting", async () => {
    const api: MockHandler = (method, path) => {
      if (method === "POST" && path === "/runs") {
        return {
          status: 503,
          body: {
            error: {
              code: "SETTING_MISSING",
              message: "Set LLM_PROVIDER in .env, then restart the app.",
              details: { setting: "LLM_PROVIDER" },
            },
          },
        };
      }
      return { status: 200, body: [] };
    };
    renderApp("/", makeFetchMock(api));
    addFiles([makeFile("Synthetic_Method_A.pdf")]);
    fireEvent.click(screen.getByRole("button", { name: /Start extraction/ }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Set LLM_PROVIDER in .env, then restart the app.");
  });

  it("a server that cannot be reached gives a plain message", async () => {
    const api: MockHandler = () => ({ status: 200, body: [] });
    const fetchMock = makeFetchMock(api);
    renderApp("/", fetchMock);
    addFiles([makeFile("Synthetic_Method_A.pdf")]);
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fireEvent.click(screen.getByRole("button", { name: /Start extraction/ }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("could not reach its server");
  });

  it("recent runs are listed with their status", async () => {
    const api: MockHandler = () => ({
      status: 200,
      body: [makeRunSummary({ name: "Synthetic finished run", status: "in_review", counts: { records: 4, to_fix: 1, to_check: 1, excluded: 0, open_errors: 2, open_warnings: 3 } })],
    });
    renderApp("/", makeFetchMock(api));
    expect(await screen.findByText("Synthetic finished run")).not.toBeNull();
    expect(screen.getByText("Ready for review")).not.toBeNull();
    expect(screen.getByText("2 to fix")).not.toBeNull();
    expect(screen.getByText("3 warnings")).not.toBeNull();
  });
});

describe("buildRunForm", () => {
  it("puts the name and one files part per file in the multipart body", () => {
    const form = buildRunForm("Synthetic run", [makeFile("a.pdf"), makeFile("b.xlsx")]);
    expect(form.get("name")).toBe("Synthetic run");
    const parts = form.getAll("files") as File[];
    expect(parts.map((part) => part.name)).toEqual(["a.pdf", "b.xlsx"]);
  });
});

describe("Start a run screen errors", () => {
  it("a failed runs list shows its error instead of the table", async () => {
    const api: MockHandler = () => ({
      status: 500,
      body: { error: { code: "UNEXPECTED_ERROR", message: "Something went wrong on the server. Try again.", details: {} } },
    });
    renderApp("/", makeFetchMock(api));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Something went wrong on the server"));
  });
});
