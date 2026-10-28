// A React hook that loads a bulk preview (GET /runs/{id}/bulk-preview) for one bulk offer,
// and loads it again when the request changes (another issue, another chosen alternative).
import { useEffect, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { getBulkPreview, type BulkPreviewRequest } from "../api/review";
import type { BulkPreview } from "../api/types";

/** What the hook gives: the preview (null while loading) and a load error. */
export interface BulkPreviewState {
  preview: BulkPreview | null;
  errorMessage: string | null;
}

/** Load the preview of a bulk request for a run. */
export function useBulkPreview(runId: string, request: BulkPreviewRequest): BulkPreviewState {
  const client = useApiClient();
  const [state, setState] = useState<BulkPreviewState>({ preview: null, errorMessage: null });
  const { mode, issueId, field, alternativeIndex } = request;

  // Load on open and whenever a request parameter changes; late answers are ignored
  useEffect(() => {
    let isCurrent = true;
    setState({ preview: null, errorMessage: null });
    getBulkPreview(client, runId, { mode, issueId, field, alternativeIndex })
      .then((preview) => isCurrent && setState({ preview, errorMessage: null }))
      .catch((error: unknown) => isCurrent && setState({ preview: null, errorMessage: describeError(error) }));
    return () => {
      isCurrent = false;
    };
  }, [client, runId, mode, issueId, field, alternativeIndex]);

  return state;
}
