// Admin calls (CONTRACTS §13): lookup list and reference data versions, uploads, apply and
// restore, and lookup workbook downloads. Admin role only: other users get 403 FORBIDDEN.
import type { ApiClient } from "./client";
import { ApiError, readApiResult } from "./errors";
import type { DataVersionInfo, DataVersionList, LookupUploadResponse, ReferenceUploadResponse } from "./types";

/** A downloaded file: its content and the name the API gave it. */
export interface DownloadedFile {
  blob: Blob;
  fileName: string;
}

/** Return the lookup list version history and the version new runs use. */
export function listLookupVersions(client: ApiClient): Promise<DataVersionList> {
  return readApiResult(client.GET("/admin/lookup-lists/versions"));
}

/** Upload an edited lookup list workbook; returns its check report and, without problems, its pending version. */
export function uploadLookupLists(client: ApiClient, file: File): Promise<LookupUploadResponse> {
  return readApiResult(
    client.POST("/admin/lookup-lists", {
      // The schema types binary uploads as strings; the file is sent as a multipart part
      body: { file: file as unknown as string },
      bodySerializer: () => buildFileForm(file),
    }),
  );
}

/** Make a pending lookup list upload current (as the next vN), or restore an older version. */
export function applyLookupVersion(client: ApiClient, versionId: string): Promise<DataVersionInfo> {
  return readApiResult(
    client.POST("/admin/lookup-lists/{version_id}/apply", { params: { path: { version_id: versionId } } }),
  );
}

/** Download the current lookup list workbook. */
export function downloadCurrentLookupLists(client: ApiClient): Promise<DownloadedFile> {
  return readDownload(client.GET("/admin/lookup-lists/current", { parseAs: "blob" }), "lookup_lists.xlsx");
}

/** Download one lookup list version's workbook. */
export function downloadLookupVersion(client: ApiClient, versionId: string): Promise<DownloadedFile> {
  return readDownload(
    client.GET("/admin/lookup-lists/versions/{version_id}/download", {
      params: { path: { version_id: versionId } },
      parseAs: "blob",
    }),
    `lookup_lists ${versionId}.xlsx`,
  );
}

/** Return the reference data version history and the version new runs use (null if none). */
export function listReferenceVersions(client: ApiClient): Promise<DataVersionList> {
  return readApiResult(client.GET("/admin/reference-data/versions"));
}

/** Upload an export of existing Consumable Types; returns its check report and pending version. */
export function uploadReferenceData(client: ApiClient, file: File): Promise<ReferenceUploadResponse> {
  return readApiResult(
    client.POST("/admin/reference-data", {
      body: { file: file as unknown as string },
      bodySerializer: () => buildFileForm(file),
    }),
  );
}

/** Make a pending reference data upload current, or restore an older version. */
export function applyReferenceVersion(client: ApiClient, versionId: string): Promise<DataVersionInfo> {
  return readApiResult(
    client.POST("/admin/reference-data/{version_id}/apply", { params: { path: { version_id: versionId } } }),
  );
}

/**
 * Return false only when the API answers an admin call with 403 (the user lacks the admin role).
 * Any other failure (server down, setting missing) keeps the Admin link: it is not a "no".
 */
export async function checkAdminAccess(client: ApiClient): Promise<boolean> {
  try {
    await listLookupVersions(client);
    return true;
  } catch (error) {
    return !isForbidden(error);
  }
}

/** Return true when an API error says the signed-in user lacks the role the call needs. */
export function isForbidden(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}

/** Build the multipart body of an admin upload: one `file` part. */
export function buildFileForm(file: File): FormData {
  const form = new FormData();
  form.append("file", file, file.name);
  return form;
}

/** What an openapi-fetch download call resolves to. */
interface DownloadResult {
  data?: unknown;
  error?: unknown;
  response: Response;
}

/** Wait for a download call; return the file and its name from Content-Disposition (or the fallback). */
async function readDownload(call: Promise<DownloadResult>, fallbackName: string): Promise<DownloadedFile> {
  // Keep the response so its headers can be read once the data is checked
  const seen: { response: Response | null } = { response: null };
  const blob = (await readApiResult(
    call.then((result) => {
      seen.response = result.response;
      return result;
    }),
  )) as Blob;
  const header = seen.response?.headers.get("Content-Disposition") ?? null;
  return { blob, fileName: readFileName(header) ?? fallbackName };
}

/** Return the file name of a Content-Disposition header (`filename="..."`), or null. */
export function readFileName(header: string | null): string | null {
  if (header === null) return null;
  const match = /filename="([^"]+)"/.exec(header);
  return match !== null ? match[1] : null;
}
