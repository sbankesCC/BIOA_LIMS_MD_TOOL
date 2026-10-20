// Run calls used by the Start and Processing screens: list, start, read and retry runs, and
// the upload limits shown on the Start screen.
// Each returns the API's data or throws an ApiError (see errors.ts).
import type { ApiClient } from "./client";
import { readApiResult } from "./errors";
import type { RunDetail, RunSummary, StartRunResponse, UploadLimits } from "./types";

/** Return every run, newest first. */
export function listRuns(client: ApiClient): Promise<RunSummary[]> {
  return readApiResult(client.GET("/runs"));
}

/** Return one run with its status, current step, documents and run issues. */
export function getRun(client: ApiClient, runId: string): Promise<RunDetail> {
  return readApiResult(client.GET("/runs/{run_id}", { params: { path: { run_id: runId } } }));
}

/** Start a new run from a name and files; the run is processed in the background. */
export function startRun(client: ApiClient, name: string, files: File[]): Promise<StartRunResponse> {
  return readApiResult(
    client.POST("/runs", {
      // The schema types binary uploads as strings; the files are sent as multipart parts
      body: { name, files: files as unknown as string[] },
      bodySerializer: () => buildRunForm(name, files),
    }),
  );
}

/** Start a new run from a failed run's files; the failed run stays as it is. */
export function retryRun(client: ApiClient, runId: string): Promise<StartRunResponse> {
  return readApiResult(
    client.POST("/runs/{run_id}/retry", { params: { path: { run_id: runId } } }),
  );
}

/** Build the multipart body of POST /runs: the name and one `files` part per file. */
export function buildRunForm(name: string, files: File[]): FormData {
  const form = new FormData();
  form.append("name", name);
  for (const file of files) {
    form.append("files", file, file.name);
  }
  return form;
}

/** Return the upload limits (null fields: no limit is set). */
export function getUploadLimits(client: ApiClient): Promise<UploadLimits> {
  return readApiResult(client.GET("/settings/upload-limits"));
}
