// A React hook behind one admin screen (lookup lists or reference data): the version history,
// the last upload's check report, Apply, Restore and downloads. A 403 on any call is reported
// to the app (the Admin link is hidden) and the screen shows a plain "no access" message.
import { useCallback, useEffect, useState } from "react";
import {
  applyLookupVersion,
  applyReferenceVersion,
  downloadCurrentLookupLists,
  downloadLookupVersion,
  isForbidden,
  listLookupVersions,
  listReferenceVersions,
  uploadLookupLists,
  uploadReferenceData,
  type DownloadedFile,
} from "../api/admin";
import { useApiClient, type ApiClient } from "../api/client";
import { describeError } from "../api/errors";
import type { DataVersionInfo, DataVersionList } from "../api/types";
import { useAdminAccess } from "./adminAccess";
import type { AdminKind, UploadReport } from "./adminVersions";
import { saveFile } from "./download";

/** The API calls of one kind of admin data. */
interface AdminCalls {
  list: (client: ApiClient) => Promise<DataVersionList>;
  upload: (client: ApiClient, file: File) => Promise<{ report: UploadReport; version: DataVersionInfo | null }>;
  apply: (client: ApiClient, versionId: string) => Promise<DataVersionInfo>;
}

// Lookup lists and reference data share the same pattern with their own endpoints
const CALLS: Record<AdminKind, AdminCalls> = {
  lookup: { list: listLookupVersions, upload: uploadLookupLists, apply: applyLookupVersion },
  reference: { list: listReferenceVersions, upload: uploadReferenceData, apply: applyReferenceVersion },
};

/** The last upload: its check report, its pending version (none with problems) and its file name. */
export interface AdminUpload {
  report: UploadReport;
  pending: DataVersionInfo | null;
  fileName: string;
}

/** Everything one admin screen shows, and its actions. */
export interface AdminData {
  versions: DataVersionList | null;
  upload: AdminUpload | null;
  isForbidden: boolean;
  isBusy: boolean;
  loadError: string | null;
  actionError: string | null;
  notice: string | null;
  uploadFile: (file: File) => Promise<void>;
  applyUpload: () => Promise<void>;
  restoreVersion: (versionId: string) => Promise<void>;
  downloadCurrent: () => Promise<void>;
  downloadVersion: (versionId: string) => Promise<void>;
}

/** Load and act on one kind of admin data. */
export function useAdminData(kind: AdminKind): AdminData {
  const client = useApiClient();
  const { reportForbidden } = useAdminAccess();
  const [versions, setVersions] = useState<DataVersionList | null>(null);
  const [upload, setUpload] = useState<AdminUpload | null>(null);
  const [isForbiddenState, setIsForbidden] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // A failed call: a 403 means no access at all; anything else is shown as a plain message
  const handleError = useCallback(
    (error: unknown, show: (message: string) => void) => {
      if (isForbidden(error)) {
        setIsForbidden(true);
        reportForbidden();
        return;
      }
      show(describeError(error));
    },
    [reportForbidden],
  );

  // Read the version history (on open and after each apply or restore)
  const loadVersions = useCallback(async () => {
    try {
      setVersions(await CALLS[kind].list(client));
      setLoadError(null);
    } catch (error) {
      handleError(error, setLoadError);
    }
  }, [client, kind, handleError]);

  useEffect(() => {
    void loadVersions();
  }, [loadVersions]);

  // Run one action: busy while it runs, its error shown under the upload card
  const runAction = async (action: () => Promise<void>) => {
    setIsBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      handleError(error, setActionError);
    } finally {
      setIsBusy(false);
    }
  };

  // Upload a file: show its report; without problems it is pending until applied
  const uploadFile = (file: File) =>
    runAction(async () => {
      setUpload(null);
      const answer = await CALLS[kind].upload(client, file);
      setUpload({ report: answer.report, pending: answer.version, fileName: file.name });
    });

  // Apply the pending upload as the next vN, then read the history again
  const applyUpload = () =>
    runAction(async () => {
      if (upload?.pending == null) return;
      const applied = await CALLS[kind].apply(client, upload.pending.upload_id);
      setUpload(null);
      setNotice(`Applied as ${applied.version_id ?? "a new version"}. New runs use it; runs already started keep their version.`);
      await loadVersions();
    });

  // Restore an older version: it becomes current again under its own name
  const restoreVersion = (versionId: string) =>
    runAction(async () => {
      const restored = await CALLS[kind].apply(client, versionId);
      setNotice(`Restored ${restored.version_id ?? versionId}. New runs use it; runs already started keep their version.`);
      await loadVersions();
    });

  // Save a downloaded workbook under the API's file name
  const saveDownload = (load: () => Promise<DownloadedFile>) =>
    runAction(async () => {
      const file = await load();
      saveFile(file.blob, file.fileName);
    });

  return {
    versions,
    upload,
    isForbidden: isForbiddenState,
    isBusy,
    loadError,
    actionError,
    notice,
    uploadFile,
    applyUpload,
    restoreVersion,
    downloadCurrent: () => saveDownload(() => downloadCurrentLookupLists(client)),
    downloadVersion: (versionId: string) => saveDownload(() => downloadLookupVersion(client, versionId)),
  };
}
