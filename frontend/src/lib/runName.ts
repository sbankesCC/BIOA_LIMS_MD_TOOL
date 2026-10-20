// Suggests a run name from the first file's name and today's date.
import { formatDay } from "./format";

// The longest run name the API accepts (maxLength of `name` in POST /runs and PATCH /runs/{run_id})
export const RUN_NAME_MAX_LENGTH = 200;

/** Return "<first file name without extension> – <today>", e.g. "Method A v2 – 16 Oct 2026". */
export function suggestRunName(fileName: string, today: Date): string {
  // Drop the extension and turn underscores into spaces
  const stem = fileName.replace(/\.[^.]+$/, "");
  const readable = stem.replace(/_+/g, " ").replace(/\s+/g, " ").trim();
  // Keep the date when a long file name has to be shortened
  const suffix = ` – ${formatDay(today)}`;
  return readable.slice(0, RUN_NAME_MAX_LENGTH - suffix.length) + suffix;
}
