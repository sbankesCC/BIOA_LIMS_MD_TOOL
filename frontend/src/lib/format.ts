// Formatting helpers for sizes, dates and times shown on the screens.

const BYTES_PER_KB = 1024;
const BYTES_PER_MB = 1024 * 1024;

/** Format a file size as "640 KB" or "2.1 MB". */
export function formatFileSize(sizeBytes: number): string {
  // Under one megabyte: whole kilobytes (at least 1)
  if (sizeBytes < BYTES_PER_MB) {
    return `${Math.max(1, Math.round(sizeBytes / BYTES_PER_KB))} KB`;
  }
  return `${(sizeBytes / BYTES_PER_MB).toFixed(1)} MB`;
}

/** Format a date as "16 Oct 2026" (used in suggested run names). */
export function formatDay(date: Date): string {
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/** Format an API timestamp as "16 Oct, 9:14 AM" in the user's time zone. */
export function formatStarted(timestamp: string): string {
  const date = new Date(timestamp);
  const day = date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const time = date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  return `${day}, ${time}`;
}
