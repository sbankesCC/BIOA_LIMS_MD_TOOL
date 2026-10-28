// What a grid cell shows (UI_SPEC §4.3 Records grid): the exported value, the placeholder of
// blank-for-now fields, "N values" for a conflict, "Missing" or "— (not found)", and the value
// as written next to the exported one when they differ.
import type { ReviewCell, RunField } from "../api/types";

/** How a cell's main text looks. */
export type CellLook = "value" | "placeholder" | "conflict" | "missing" | "not_found";

/** A cell's text, how it looks, and the value as written when it differs from the exported one. */
export interface CellDisplay {
  text: string;
  look: CellLook;
  writtenText: string | null;
}

/** Return true when a cell has no exported value. */
function isBlank(value: string | null): boolean {
  return value === null || value.trim().length === 0;
}

/** Return what to show after the arrow when the value as written was not exported as is. */
function describeExported(cell: ReviewCell, field: RunField | null): string {
  if (!isBlank(cell.value)) {
    return cell.value ?? "";
  }
  return field?.allowed_values.length ? "choose from list" : "enter a value";
}

/** Return the display of one grid cell. */
export function describeCell(cell: ReviewCell, field: RunField | null): CellDisplay {
  // Blank-for-now fields: the API's placeholder, display only (exported blank)
  if (cell.is_placeholder) {
    return { text: cell.display_value ?? "", look: "placeholder", writtenText: null };
  }
  // An unresolved conflict: how many values the documents give
  if (cell.alternatives.length > 1 && isBlank(cell.value)) {
    return { text: `${cell.alternatives.length} values`, look: "conflict", writtenText: null };
  }
  // A value as written that differs from the exported value: "as written → exported"
  if (cell.written_value !== null) {
    return { text: describeExported(cell, field), look: isBlank(cell.value) ? "missing" : "value", writtenText: cell.written_value };
  }
  if (isBlank(cell.value)) {
    // Red cells need a value; otherwise the optional value was not found
    return cell.color === "red"
      ? { text: "Missing", look: "missing", writtenText: null }
      : { text: "— (not found)", look: "not_found", writtenText: null };
  }
  return { text: cell.display_value ?? cell.value ?? "", look: "value", writtenText: null };
}
