// A React hook that loads the run's bulk actions (GET /runs/{id}/bulk-actions) for Undo, and
// loads them again whenever the review view is reloaded or the pending state changes.
import { useCallback, useEffect, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { listBulkActions } from "../api/review";
import type { BulkActionSummary, ReviewView } from "../api/types";

/** What the hook gives: the bulk actions (newest first), a load error, and a reload call. */
export interface BulkActionsState {
  actions: BulkActionSummary[];
  errorMessage: string | null;
  reload: () => Promise<void>;
}

/**
 * Load the run's bulk actions. A bulk action, undo, exclude, restore and re-check all reload
 * the view (or change the pending state), so the list is read again after each of them.
 */
export function useBulkActions(runId: string, view: ReviewView, hasPendingChanges: boolean): BulkActionsState {
  const client = useApiClient();
  const [actions, setActions] = useState<BulkActionSummary[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Read the list; a failed read keeps the last list and shows the error
  const reload = useCallback(async () => {
    try {
      setActions(await listBulkActions(client, runId));
      setErrorMessage(null);
    } catch (error) {
      setErrorMessage(describeError(error));
    }
  }, [client, runId]);

  // Read on open and after every view reload or pending change; late answers are ignored
  useEffect(() => {
    let isCurrent = true;
    listBulkActions(client, runId)
      .then((loaded) => {
        if (!isCurrent) return;
        setActions(loaded);
        setErrorMessage(null);
      })
      .catch((error: unknown) => isCurrent && setErrorMessage(describeError(error)));
    return () => {
      isCurrent = false;
    };
  }, [client, runId, view, hasPendingChanges]);

  return { actions, errorMessage, reload };
}
