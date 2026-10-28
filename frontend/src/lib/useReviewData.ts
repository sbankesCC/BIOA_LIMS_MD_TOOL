// A React hook that loads what the Review screen shows: the run, the review view and the
// run's fields. `reload` reads them again (after a re-check) and returns the new view;
// `refreshRun` reads only the run (verified label, exports).
import { useCallback, useEffect, useRef, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { getReviewView, getRunFields } from "../api/review";
import { getRun } from "../api/runs";
import type { ReviewView, RunDetail, RunFieldList } from "../api/types";

/** What the hook gives: the loaded data (null until loaded), a load error, and reload. */
export interface ReviewData {
  run: RunDetail | null;
  view: ReviewView | null;
  fieldList: RunFieldList | null;
  errorMessage: string | null;
  reload: () => Promise<ReviewView | null>;
  refreshRun: () => Promise<void>;
  replaceRun: (run: RunDetail) => void;
}

/** Load the run, its review view and its fields, and reload them on request. */
export function useReviewData(runId: string): ReviewData {
  const client = useApiClient();
  const [run, setRun] = useState<RunDetail | null>(null);
  const [view, setView] = useState<ReviewView | null>(null);
  const [fieldList, setFieldList] = useState<RunFieldList | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Answers that arrive after the screen closed are ignored
  const isMounted = useRef(true);

  const reload = useCallback(async (): Promise<ReviewView | null> => {
    try {
      // The three reads do not depend on each other
      const [loadedRun, loadedView, loadedFields] = await Promise.all([
        getRun(client, runId),
        getReviewView(client, runId),
        getRunFields(client, runId),
      ]);
      if (!isMounted.current) return null;
      setRun(loadedRun);
      setView(loadedView);
      setFieldList(loadedFields);
      setErrorMessage(null);
      return loadedView;
    } catch (error) {
      if (isMounted.current) setErrorMessage(describeError(error));
      return null;
    }
  }, [client, runId]);

  // Read only the run again (verified label, exports) after a change or an export
  const refreshRun = useCallback(async (): Promise<void> => {
    try {
      const loadedRun = await getRun(client, runId);
      if (isMounted.current) setRun(loadedRun);
    } catch (error) {
      if (isMounted.current) setErrorMessage(describeError(error));
    }
  }, [client, runId]);

  // First load when the screen opens
  useEffect(() => {
    isMounted.current = true;
    void reload();
    return () => {
      isMounted.current = false;
    };
  }, [reload]);

  return { run, view, fieldList, errorMessage, reload, refreshRun, replaceRun: setRun };
}
