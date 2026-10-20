// Review screen calls: the review view, the run's fields, one record, source chunks and page
// images, saving changes, re-checking and renaming. Each returns data or throws an ApiError.
import type { ApiClient } from "./client";
import { readApiResult } from "./errors";
import type {
  Change,
  ChunkSource,
  RecheckResult,
  RecordDetail,
  ReviewView,
  RunDetail,
  RunFieldList,
  SaveResult,
} from "./types";

/** Return the flattened review grid: rows, run issues and counts. */
export function getReviewView(client: ApiClient, runId: string): Promise<ReviewView> {
  return readApiResult(
    client.GET("/runs/{run_id}/records", { params: { path: { run_id: runId } } }),
  );
}

/** Return the run's fields in loader order, with the values each dropdown may offer. */
export function getRunFields(client: ApiClient, runId: string): Promise<RunFieldList> {
  return readApiResult(
    client.GET("/runs/{run_id}/fields", { params: { path: { run_id: runId } } }),
  );
}

/** Return one record with its sections and its issues (with details) of every status. */
export function getRecord(client: ApiClient, runId: string, recordId: string): Promise<RecordDetail> {
  return readApiResult(
    client.GET("/runs/{run_id}/records/{record_id}", {
      params: { path: { run_id: runId, record_id: recordId } },
    }),
  );
}

/** Return a source chunk's text (null for a scanned page) and where it is. */
export function getChunk(client: ApiClient, runId: string, chunkId: string): Promise<ChunkSource> {
  return readApiResult(
    client.GET("/runs/{run_id}/chunks/{chunk_id}", {
      params: { path: { run_id: runId, chunk_id: chunkId } },
    }),
  );
}

/** Return the PNG of a scanned page chunk as a Blob. */
export function getChunkImage(client: ApiClient, runId: string, chunkId: string): Promise<Blob> {
  return readApiResult(
    client.GET("/runs/{run_id}/chunks/{chunk_id}/image", {
      params: { path: { run_id: runId, chunk_id: chunkId } },
      parseAs: "blob",
    }),
  ) as Promise<Blob>;
}

/** Store changes as pending; the API ignores a change ID it already stored. */
export function saveChanges(client: ApiClient, runId: string, changes: Change[]): Promise<SaveResult> {
  return readApiResult(
    client.POST("/runs/{run_id}/changes", {
      params: { path: { run_id: runId } },
      // The API stores the signed-in user; the body's user is not used, so it is left empty
      body: { user: "", timestamp: new Date().toISOString(), changes },
    }),
  );
}

/** Apply the pending changes and run the validation again; returns the new counts. */
export function recheckRun(client: ApiClient, runId: string): Promise<RecheckResult> {
  return readApiResult(
    client.POST("/runs/{run_id}/recheck", { params: { path: { run_id: runId } } }),
  );
}

/** Give the run a new name; returns the updated run. */
export function renameRun(client: ApiClient, runId: string, name: string): Promise<RunDetail> {
  return readApiResult(
    client.PATCH("/runs/{run_id}", { params: { path: { run_id: runId } }, body: { name } }),
  );
}
