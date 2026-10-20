// Whether the signed-in user may use the admin screens. There is no "who am I" endpoint, so
// access is known only from the API: a 403 on an admin call hides the Admin link.
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { checkAdminAccess } from "../api/admin";
import { useApiClient } from "../api/client";

/** What the app knows about admin access, and how a screen reports a 403. */
export interface AdminAccess {
  hasAccess: boolean;
  reportForbidden: () => void;
}

// Until the API says otherwise the Admin link is shown (UI_SPEC §3: always visible in the pilot)
export const AdminAccessContext = createContext<AdminAccess>({ hasAccess: true, reportForbidden: () => undefined });

/** Return the nearest admin access state. */
export function useAdminAccess(): AdminAccess {
  return useContext(AdminAccessContext);
}

/** Ask the API once at start whether admin calls are allowed, and keep any 403 a screen reports. */
export function useAdminAccessState(): AdminAccess {
  const client = useApiClient();
  const [hasAccess, setHasAccess] = useState(true);

  // One admin call at start: only a 403 hides the Admin link
  useEffect(() => {
    let isActive = true;
    void checkAdminAccess(client).then((isAllowed) => {
      if (isActive && !isAllowed) setHasAccess(false);
    });
    return () => {
      isActive = false;
    };
  }, [client]);

  // An admin screen that gets a 403 hides the link too
  const reportForbidden = useCallback(() => setHasAccess(false), []);
  return { hasAccess, reportForbidden };
}
