// A React hook for "Export to Excel" (UI_SPEC §4.5): re-check saved changes, create the export
// (POST /runs/{id}/exports), read the run again, then download the loader and the audit
// workbook through the API client and save them under the display names the API gives.
import { useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { createExport, downloadAudit, downloadLoader } from "../api/exports";
import type { RunExport } from "../api/types";
import { saveFile } from "./download";
import type { ReviewSession } from "./useReviewSession";

/** What the hook gives: the export made on this screen, progress, an error and the action. */
export interface RunExportState {
  latest: RunExport | null;
  isExporting: boolean;
  errorMessage: string | null;
  exportRun: () => Promise<void>;
}

/** Hold the export state of one run. */
export function useRunExport(runId: string, session: ReviewSession, refreshRun: () => Promise<void>): RunExportState {
  const client = useApiClient();
  const [latest, setLatest] = useState<RunExport | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Export, then save both files; any failure is shown in plain language
  const exportRun = async () => {
    setIsExporting(true);
    setErrorMessage(null);
    try {
      // The API re-checks saved changes too; doing it here also refreshes the grid
      if (session.hasPendingChanges) await session.recheckNow();
      const created = await createExport(client, runId);
      setLatest(created);
      await refreshRun();
      saveFile(await downloadLoader(client, runId, created.export_id), created.loader_file_name);
      saveFile(await downloadAudit(client, runId, created.export_id), created.audit_file_name);
    } catch (error) {
      setErrorMessage(describeError(error));
    } finally {
      setIsExporting(false);
    }
  };

  return { latest, isExporting, errorMessage, exportRun };
}
