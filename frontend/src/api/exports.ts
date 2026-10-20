// Export calls: create an export (loader + audit workbook) and download either file as a Blob.
// The run's export list comes with GET /runs/{id}; files carry display names, never storage paths.
import type { ApiClient } from "./client";
import { readApiResult } from "./errors";
import type { RunExport } from "./types";

/** Write a new export of the run (a draft unless the run is verified); returns its file names. */
export function createExport(client: ApiClient, runId: string): Promise<RunExport> {
  return readApiResult(
    client.POST("/runs/{run_id}/exports", { params: { path: { run_id: runId } } }),
  );
}

/** Download an export's loader workbook as a Blob. */
export function downloadLoader(client: ApiClient, runId: string, exportId: string): Promise<Blob> {
  return readApiResult(
    client.GET("/runs/{run_id}/exports/{export_id}/loader", {
      params: { path: { run_id: runId, export_id: exportId } },
      parseAs: "blob",
    }),
  ) as Promise<Blob>;
}

/** Download an export's audit workbook as a Blob. */
export function downloadAudit(client: ApiClient, runId: string, exportId: string): Promise<Blob> {
  return readApiResult(
    client.GET("/runs/{run_id}/exports/{export_id}/audit", {
      params: { path: { run_id: runId, export_id: exportId } },
      parseAs: "blob",
    }),
  ) as Promise<Blob>;
}
