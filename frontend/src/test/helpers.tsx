// Test helpers: a mocked fetch that answers by method and path, synthetic run data,
// and a render function that mounts the app at an address with that fetch.
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { App } from "../App";
import { ApiClientContext, createApiClient } from "../api/client";
import type { RunDetail, RunSummary } from "../api/types";
import { HOW_IT_WORKS_SEEN_KEY } from "../components/HowItWorksDialog";

// Tests use an absolute API address: Node's Request needs one
const TEST_BASE_URL = "http://localhost/api";

/** One answer of the mocked API: a status and a JSON body. */
export interface MockAnswer {
  status: number;
  body: unknown;
}

/** A handler picks the answer for a request from its method and path (without /api). */
export type MockHandler = (method: string, path: string, request: Request) => MockAnswer;

/** Return a JSON Response like the back end sends. */
export function jsonResponse(answer: MockAnswer): Response {
  return new Response(JSON.stringify(answer.body), {
    status: answer.status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Make a mocked fetch that answers every request through the handler. */
export function makeFetchMock(handler: MockHandler) {
  return vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname.replace(/^\/api/, "");
    return jsonResponse(handler(request.method, path, request));
  });
}

/** Render the whole app at an address, with the API answered by a mocked fetch. */
export function renderApp(path: string, fetchMock: (request: Request) => Promise<Response>) {
  // Screen tests mark the popup as seen; the popup has its own tests
  window.localStorage.setItem(HOW_IT_WORKS_SEEN_KEY, "yes");
  const client = createApiClient({ baseUrl: TEST_BASE_URL, fetch: fetchMock });
  return render(
    <ApiClientContext.Provider value={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </ApiClientContext.Provider>,
  );
}

// Counts of a run with no records yet
const EMPTY_COUNTS = {
  records: 0,
  to_fix: 0,
  to_check: 0,
  excluded: 0,
  open_errors: 0,
  open_warnings: 0,
  resolved_issues: 0,
  total_issues: 0,
};

/** Return a synthetic run summary, changed by `overrides`. */
export function makeRunSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "run_0001",
    name: "Synthetic run",
    created_by: "test-user",
    created_at: "2026-10-16T09:14:00Z",
    status: "extracting",
    retry_of: null,
    is_verified: false,
    verified_by: null,
    verified_at: null,
    counts: EMPTY_COUNTS,
    failure_reason: null,
    latest_export: null,
    ...overrides,
  };
}

/** Return a synthetic run detail, changed by `overrides`. */
export function makeRunDetail(overrides: Partial<RunDetail> = {}): RunDetail {
  return {
    ...makeRunSummary(),
    current_step: "extracting",
    config_versions: {
      field_rules: "test-1",
      issue_catalogue: "test-1",
      lookup_lists: "v-test",
      dfd_template: "test-1",
      reference_data_mapping: "test-1",
      prompts: {},
    },
    reference_data_version: null,
    models: {},
    has_pending_changes: false,
    documents: [],
    run_issues: [],
    exports: [],
    ...overrides,
  };
}
