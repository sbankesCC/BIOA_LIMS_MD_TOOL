// Review screen calls: the review view, the run's fields, one record, source chunks and page
// images, bulk previews and the bulk action list, saving changes, re-checking, Verify and
// renaming. Each returns data or throws an ApiError.
import type { ApiClient } from "./client";
import { readApiResult } from "./errors";
import type {
  BulkActionSummary,
  BulkMode,
  BulkPreview,
  Change,
  ChunkSource,
  RecheckResult,
  RecordDetail,
  ReviewView,
  RunDetail,
  RunFieldList,
  SaveResult,
  VerifyResult,
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

/** What a bulk preview starts from: the mode and the parameters that mode needs. */
export interface BulkPreviewRequest {
  mode: BulkMode;
  issueId?: string | null;
  field?: string | null;
  alternativeIndex?: number | null;
}

/** Return the records a bulk action would touch (excluded records never match). */
export function getBulkPreview(client: ApiClient, runId: string, request: BulkPreviewRequest): Promise<BulkPreview> {
  return readApiResult(
    client.GET("/runs/{run_id}/bulk-preview", {
      params: {
        path: { run_id: runId },
        query: {
          mode: request.mode,
          issue_id: request.issueId ?? undefined,
          field: request.field ?? undefined,
          alternative_index: request.alternativeIndex ?? undefined,
        },
      },
    }),
  );
}

/** Re-check, then set the verified label; or return the issues that block it. */
export function verifyRun(client: ApiClient, runId: string): Promise<VerifyResult> {
  return readApiResult(
    client.POST("/runs/{run_id}/verify", { params: { path: { run_id: runId } } }),
  );
}

/** Return the run's bulk actions, newest first, with whether each was or can be undone. */
export function listBulkActions(client: ApiClient, runId: string): Promise<BulkActionSummary[]> {
  return readApiResult(
    client.GET("/runs/{run_id}/bulk-actions", { params: { path: { run_id: runId } } }),
  );
}
