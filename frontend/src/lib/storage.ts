// Safe access to the browser's localStorage for small per-user conveniences.
// Storage can be blocked or missing (private windows, tests), so every call is guarded.

/** Return the stored text for a key, or null when it is missing or storage is unavailable. */
export function readStoredValue(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

/** Store text for a key; does nothing when storage is unavailable. */
export function writeStoredValue(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage is blocked: the app works the same, it just does not remember
  }
}
