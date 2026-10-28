// Remembers which run issues the user dismissed from a run's banner (UI_SPEC §4.3), per run,
// in localStorage. A run issue that appears later shows the banner again.
import { readStoredValue, writeStoredValue } from "./storage";

// Key prefix; the run ID is added to it
const DISMISSED_KEY_PREFIX = "consumable-type-extractor.banner-dismissed.";

/** Return the storage key of a run's dismissed banner. */
export function makeBannerKey(runId: string): string {
  return `${DISMISSED_KEY_PREFIX}${runId}`;
}

/** Return the run issue IDs dismissed for a run (empty when none or storage is blocked). */
export function readDismissedIssueIds(runId: string): string[] {
  const stored = readStoredValue(makeBannerKey(runId));
  if (stored === null) {
    return [];
  }
  // The value is a JSON list; anything else is treated as nothing dismissed
  try {
    const parsed: unknown = JSON.parse(stored);
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

/** Remember that these run issues were dismissed for the run. */
export function writeDismissedIssueIds(runId: string, issueIds: string[]): void {
  writeStoredValue(makeBannerKey(runId), JSON.stringify(issueIds));
}
