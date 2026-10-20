// Which files a run accepts, checked in the browser before upload.
// The back end checks the same rule again (POST /runs answers FILE_REJECTED).

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
