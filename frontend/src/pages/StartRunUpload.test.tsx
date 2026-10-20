// Tests that the Start screen uploads in-memory copies of the picked files. Chrome refuses to
// send a picked file that changed on disk afterwards (ERR_UPLOAD_FILE_CHANGED), so the request
// never left the browser and the screen said the server could not be reached.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UNREADABLE_FILE_MESSAGE } from "../lib/fileRules";
import { makeFetchMock, makeRunDetail, renderApp, type MockHandler } from "../test/helpers";

// The files each startRun call received, recorded while the real call still runs
const startedWith = vi.hoisted(() => [] as File[][]);

vi.mock("../api/runs", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/runs")>();
  return {
    ...original,
    startRun: (...args: Parameters<typeof original.startRun>) => {
      startedWith.push(args[2]);
      return original.startRun(...args);
    },
  };
});

/** A synthetic picked file that the browser can no longer read once it "changes on disk". */
class FileOnDisk extends File {
  isChanged = false;
  isUnreadable = false;

  /** Read the bytes, failing like the browser once the file changed or cannot be read. */
  override arrayBuffer(): Promise<ArrayBuffer> {
    if (this.isChanged || this.isUnreadable) {
      return Promise.reject(new DOMException("The file changed after it was picked.", "NotReadableError"));
    }
    return super.arrayBuffer();
  }
}

/** An API that starts run_0007 and then reports it processing. */
const startingApi: MockHandler = (method, path) => {
  if (method === "POST" && path === "/runs") return { status: 202, body: { run_id: "run_0007", retry_of: null } };
  if (method === "GET" && path === "/runs/run_0007") {
    return { status: 200, body: makeRunDetail({ run_id: "run_0007", name: "Started run" }) };
  }
  return { status: 200, body: [] };
};

/** Add files through the hidden file input, as "Browse files" does. */
function addFiles(files: File[]) {
  fireEvent.change(screen.getByLabelText("Add files"), { target: { files } });
}

describe("Start screen upload of picked files", () => {
  it("a file changed on disk after it was picked is still uploaded from its in-memory copy", async () => {
    startedWith.length = 0;
    renderApp("/", makeFetchMock(startingApi));
    const picked = new FileOnDisk([new Uint8Array([1, 2, 3])], "Synthetic_Method_A.docx", { lastModified: 1 });
    addFiles([picked]);
    const start = screen.getByRole("button", { name: /Start extraction/ }) as HTMLButtonElement;
    await waitFor(() => expect(start.disabled).toBe(false));
    // Word or OneDrive touches the file after it was added
    picked.isChanged = true;
    fireEvent.click(start);
    expect(await screen.findByRole("heading", { name: "Started run" })).not.toBeNull();
    // The upload got a readable copy with the same name and bytes, not the changed original
    const [uploaded] = startedWith[0];
    expect(uploaded).not.toBe(picked);
    expect(uploaded.name).toBe("Synthetic_Method_A.docx");
    expect(Array.from(new Uint8Array(await uploaded.arrayBuffer()))).toEqual([1, 2, 3]);
  });

  it("a file that cannot be read when added is listed with a plain message and not sent", async () => {
    renderApp("/", makeFetchMock(startingApi));
    const locked = new FileOnDisk([new Uint8Array([1])], "Synthetic_Locked.xlsx", { lastModified: 1 });
    locked.isUnreadable = true;
    addFiles([locked]);
    expect(await screen.findByText(UNREADABLE_FILE_MESSAGE)).not.toBeNull();
    const start = screen.getByRole("button", { name: /Start extraction/ }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
    expect(screen.getByText("Add at least one Word, PDF or Excel file to start.")).not.toBeNull();
  });
});
