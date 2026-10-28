// A React hook that loads the runs list once, for Recent runs and the Runs page.
import { useEffect, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { listRuns } from "../api/runs";
import type { RunSummary } from "../api/types";

/** What the hook gives: the runs (null while loading) and an error message, if any. */
export interface RunListState {
  runs: RunSummary[] | null;
  errorMessage: string | null;
}

/** Load every run (newest first) when the screen opens. */
export function useRunList(): RunListState {
  const client = useApiClient();
  const [state, setState] = useState<RunListState>({ runs: null, errorMessage: null });

  useEffect(() => {
    // Ignore an answer that arrives after the screen closed
    let isActive = true;
    listRuns(client)
      .then((runs) => isActive && setState({ runs, errorMessage: null }))
      .catch((error: unknown) => isActive && setState({ runs: null, errorMessage: describeError(error) }));
    return () => {
      isActive = false;
    };
  }, [client]);

  return state;
}
