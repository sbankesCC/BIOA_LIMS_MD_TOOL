// A React hook that loads one run and asks again every few seconds while it is processing.
// Polling stops when the run reaches review or fails, when loading fails, or when the screen closes.
import { useCallback, useEffect, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { getRun } from "../api/runs";
import type { RunDetail } from "../api/types";
import { isProcessing } from "./processingSteps";

// How often a processing run is read again
export const DEFAULT_POLL_INTERVAL_MS = 2000;

/** What the hook gives: the latest run (null until loaded), an error message, reload, and replaceRun. */
export interface RunPollingState {
  run: RunDetail | null;
  errorMessage: string | null;
  reload: () => void;
  // Show a run the API just gave back (e.g. after a rename) without waiting for the next poll
  replaceRun: (run: RunDetail) => void;
}

/** Load a run and keep it fresh while it is processing. */
export function useRunPolling(runId: string, intervalMs: number): RunPollingState {
  const client = useApiClient();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [loadCount, setLoadCount] = useState(0);

  useEffect(() => {
    // Answers that arrive after the screen closed are ignored, and the next poll is cancelled
    let isActive = true;
    let timer: number | undefined;
    const load = async () => {
      try {
        const loaded = await getRun(client, runId);
        if (!isActive) return;
        setRun(loaded);
        setErrorMessage(null);
        // Ask again later only while the run is still being processed
        if (isProcessing(loaded.status)) {
          timer = window.setTimeout(load, intervalMs);
        }
      } catch (error) {
        if (isActive) setErrorMessage(describeError(error));
      }
    };
    void load();
    return () => {
      isActive = false;
      window.clearTimeout(timer);
    };
  }, [client, runId, intervalMs, loadCount]);

  // Load again after an error (the "Try again" button)
  const reload = useCallback(() => setLoadCount((count) => count + 1), []);
  return { run, errorMessage, reload, replaceRun: setRun };
}
