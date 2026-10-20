// Which files a run accepts, checked in the browser before upload, and the upload limits text.
// The back end checks the same rules again (POST /runs answers FILE_REJECTED).
import type { UploadLimits } from "../api/types";

/** One accepted file type: its extension and the word shown in the file list. */
interface AcceptedType {
  extension: string;
  label: string;
}

// The document types POST /runs accepts (from the API description of `files`)
const ACCEPTED_TYPES: AcceptedType[] = [
  { extension: ".docx", label: "Word" },
  { extension: ".pdf", label: "PDF" },
  { extension: ".xlsx", label: "Excel" },
];

// The value for the file input's `accept` attribute
export const ACCEPT_ATTRIBUTE = ACCEPTED_TYPES.map((type) => type.extension).join(",");

// The message shown next to a refused file
export const REJECTED_FILE_MESSAGE = "Not added: only Word, PDF and Excel files are accepted";

/** Return the type label ("Word", "PDF", "Excel") of an accepted file, or null if refused. */
export function findFileTypeLabel(fileName: string): string | null {
  const lowerName = fileName.toLowerCase();
  const match = ACCEPTED_TYPES.find((type) => lowerName.endsWith(type.extension));
  return match ? match.label : null;
}

/** Return true for a limit the API set (a number); null (or a missing value) means no limit. */
function isLimitSet(limit: number | null | undefined): limit is number {
  return typeof limit === "number";
}

/** Return the limit phrases to show, e.g. ["25 MB per file", "10 files per run"]; none when unset. */
export function describeUploadLimits(limits: UploadLimits | null): string[] {
  if (limits === null) return [];
  const phrases: string[] = [];
  if (isLimitSet(limits.max_file_size_mb)) phrases.push(`${limits.max_file_size_mb} MB per file`);
  if (isLimitSet(limits.max_files_per_run)) {
    phrases.push(`${limits.max_files_per_run} ${limits.max_files_per_run === 1 ? "file" : "files"} per run`);
  }
  return phrases;
}
