// A React hook that loads the upload limits (GET /settings/upload-limits) for the Start screen.
// A failed read shows no limits: the back end still checks them when the run is started.
import { useEffect, useState } from "react";
import { useApiClient } from "../api/client";
import { getUploadLimits } from "../api/runs";
import type { UploadLimits } from "../api/types";

/** Load the upload limits once; null while loading or when they could not be read. */
export function useUploadLimits(): UploadLimits | null {
  const client = useApiClient();
  const [limits, setLimits] = useState<UploadLimits | null>(null);

  // Read once on open; an answer after the screen closed is ignored
  useEffect(() => {
    let isActive = true;
    getUploadLimits(client)
      .then((loaded) => isActive && setLimits(loaded))
      .catch(() => isActive && setLimits(null));
    return () => {
      isActive = false;
    };
  }, [client]);

  return limits;
}
