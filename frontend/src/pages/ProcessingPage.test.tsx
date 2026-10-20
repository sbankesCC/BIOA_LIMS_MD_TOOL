// Tests for the Processing screen: steps mapped from the run status, polling until review,
// and the failed state with its reason and Retry.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ApiClientContext, createApiClient } from "../api/client";
import type { RunDetail, RunStatus } from "../api/types";
import { makeFetchMock, makeRunDetail, renderApp, type MockHandler } from "../test/helpers";
import { ProcessingPage } from "./ProcessingPage";

/** Return the state (done, current, waiting) of each of the six steps, in order. */
function readStepStates(): string[] {
  const list = screen.getByRole("list", { name: "Processing steps" });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.getAttribute("data-state") ?? "");
}

/** An API that always answers GET /runs/run_0001 with the given run. */
function answerWith(run: RunDetail): MockHandler {
  return () => ({ status: 200, body: run });
}

describe("Processing screen step mapping", () => {
  // Expected states of the six steps for each processing status
  const cases: [RunStatus, string[]][] = [
    ["ingesting", ["current", "waiting", "waiting", "waiting", "waiting", "waiting"]],
    ["extracting", ["done", "current", "waiting", "waiting", "waiting", "waiting"]],
    ["verifying_extraction", ["done", "done", "current", "current", "waiting", "waiting"]],
    ["transforming", ["done", "done", "done", "done", "current", "waiting"]],
    ["validating", ["done", "done", "done", "done", "done", "current"]],
    ["in_review", ["done", "done", "done", "done", "done", "done"]],
  ];

  it.each(cases)("status %s gives steps %j", async (status, expected) => {
    const run = makeRunDetail({ status, current_step: status });
    renderApp("/runs/run_0001", makeFetchMock(answerWith(run)));
    await screen.findByRole("heading", { name: "Synthetic run" });
    expect(readStepStates()).toEqual(expected);
  });

  it("a run in review links to its Review screen", async () => {
    renderApp("/runs/run_0001", makeFetchMock(answerWith(makeRunDetail({ status: "in_review", current_step: null }))));
    const link = await screen.findByRole("link", { name: /Review the records/ });
    expect(link.getAttribute("href")).toBe("/runs/run_0001/review");
  });

  it("the current step is marked for screen readers", async () => {
    renderApp("/runs/run_0001", makeFetchMock(answerWith(makeRunDetail({ status: "extracting" }))));
    const current = await screen.findByText("Extracting consumables");
    expect(current.closest("li")?.getAttribute("aria-current")).toBe("step");
  });
});

describe("Processing screen polling", () => {
  it("reads the run again until it is ready for review", async () => {
    // First answer: extracting; every later answer: in review
    let callCount = 0;
    const api: MockHandler = () => {
      callCount += 1;
      const status: RunStatus = callCount === 1 ? "extracting" : "in_review";
      return { status: 200, body: makeRunDetail({ status }) };
    };
    const fetchMock = makeFetchMock(api);
    const client = createApiClient({ baseUrl: "http://localhost/api", fetch: fetchMock });
    render(
      <ApiClientContext.Provider value={client}>
        <MemoryRouter>
          <ProcessingPage runId="run_0001" pollIntervalMs={10} />
        </MemoryRouter>
      </ApiClientContext.Provider>,
    );
    expect(await screen.findByRole("heading", { name: "Working on your documents" })).not.toBeNull();
    expect(await screen.findByRole("heading", { name: "Your run is ready for review" })).not.toBeNull();
    // Polling stopped once the run was ready
    const callsWhenReady = fetchMock.mock.calls.length;
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(fetchMock.mock.calls.length).toBe(callsWhenReady);
  });
});

describe("Processing screen failed state", () => {
  // A failed run with one open run-level error issue
  const failedRun = makeRunDetail({
    status: "failed",
    current_step: null,
    run_issues: [
      {
        issue_id: "iss_test",
        code: "NO_READABLE_DOCUMENTS",
        severity: "error",
        record_id: null,
        field: null,
        message: "None of the files could be read. Check the files and start a new run.",
        individual_review: false,
        details: {},
        status: "open",
        closed_by: null,
      },
    ],
  });

  it("shows the reason in plain language and a Retry button", async () => {
    renderApp("/runs/run_0001", makeFetchMock(answerWith(failedRun)));
    expect(await screen.findByRole("heading", { name: /This run could not be finished/ })).not.toBeNull();
    expect(screen.getByText("None of the files could be read. Check the files and start a new run.")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).not.toBeNull();
    expect(screen.getByText("Failed", { exact: false })).not.toBeNull();
  });

  it("Retry starts a new run and opens it", async () => {
    const api: MockHandler = (method, path) => {
      if (method === "POST" && path === "/runs/run_0001/retry") {
        return { status: 202, body: { run_id: "run_0002", retry_of: "run_0001" } };
      }
      if (path === "/runs/run_0002") {
        return { status: 200, body: makeRunDetail({ run_id: "run_0002", name: "Retried run", retry_of: "run_0001" }) };
      }
      return { status: 200, body: failedRun };
    };
    const fetchMock = makeFetchMock(api);
    renderApp("/runs/run_0001", fetchMock);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Retried run" })).not.toBeNull();
    expect(screen.getByText(/Retry of run_0001/)).not.toBeNull();
    const retries = fetchMock.mock.calls.filter(([request]) => request.method === "POST");
    expect(new URL(retries[0][0].url).pathname).toBe("/api/runs/run_0001/retry");
  });

  it("a refused retry shows the API's message", async () => {
    const api: MockHandler = (method) => {
      if (method === "POST") {
        return {
          status: 409,
          body: { error: { code: "RUN_NOT_FAILED", message: "Run run_0001 has not failed, so it cannot be retried.", details: {} } },
        };
      }
      return { status: 200, body: failedRun };
    };
    renderApp("/runs/run_0001", makeFetchMock(api));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("has not failed, so it cannot be retried");
  });

  it("an unknown run shows the not-found message", async () => {
    const api: MockHandler = () => ({
      status: 404,
      body: { error: { code: "RUN_NOT_FOUND", message: "Run run_0001 was not found. Check the run ID.", details: {} } },
    });
    renderApp("/runs/run_0001", makeFetchMock(api));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("was not found");
    expect(screen.getByRole("button", { name: "Try again" })).not.toBeNull();
  });
});
