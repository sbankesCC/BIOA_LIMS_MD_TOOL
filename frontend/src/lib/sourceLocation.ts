// Formats where a source chunk is (document · section · page, or sheet rows) for links
// such as "Found in" and the source viewer heading.
import type { SourceLocation } from "../api/types";

/** Return "file · section · p. N" (or "file · sheet rows 12-20"); unknown parts are left out. */
export function formatLocation(location: SourceLocation): string {
  const parts: string[] = [location.file_name ?? location.document_id ?? location.chunk_id];
  // Word headings and PDF pages
  if (location.section) {
    parts.push(location.section);
  }
  if (location.page !== null && location.page !== undefined) {
    parts.push(`p. ${location.page}`);
  }
  // Excel sheets and their rows
  if (location.sheet) {
    parts.push(location.row_range ? `${location.sheet} rows ${location.row_range}` : location.sheet);
  }
  return parts.join(" · ");
}

// Word section paths are written "Heading > Subheading > Section"
const SECTION_PATH_SEPARATOR = " > ";

/** Return the location with only the last heading of a section path, for narrow places (grid, panel). */
export function formatShortLocation(location: SourceLocation): string {
  const section = location.section?.split(SECTION_PATH_SEPARATOR).pop() ?? location.section;
  return formatLocation({ ...location, section });
}
