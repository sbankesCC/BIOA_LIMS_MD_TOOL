// Helpers for the possible-duplicate comparison: how each existing LabVantage type matched (in
// plain words) and which of this record's values to show next to the existing types.
// The match words are the tool's contract (CONTRACTS §3a and §5), not client data.
import type { ReviewRow, RunField } from "../api/types";

/** One of this record's values for the comparison: the field's column and the shown value. */
export interface RecordValue {
  column: string;
  value: string;
}

// Plain explanations of each way a name can match an existing type
const MATCH_TEXTS: Record<string, string> = {
  exact: "Exactly the same name",
  normalized: "Same name apart from capitals, spaces or °",
  same: "The duplicate checker thinks it is the same type",
  unsure: "The duplicate checker could not tell",
};

/** Return the plain explanation of how a candidate matched ("—" when the API gives none). */
export function describeMatch(match: string | null | undefined): string {
  if (match === null || match === undefined || match.length === 0) return "—";
  return MATCH_TEXTS[match] ?? match;
}

/** Return an existing type's attribute as text, or "—" when the reference data has none. */
export function showAttribute(value: string | null | undefined): string {
  return value !== null && value !== undefined && value.length > 0 ? value : "—";
}

/**
 * Return this record's extracted values (not the name, not blank or placeholder ones) in field order.
 * The fields are chosen by their role and flag from `/fields`, never by name: the API does not say
 * which record field matches an existing type's description or class.
 */
export function listRecordValues(row: ReviewRow | null, fields: RunField[]): RecordValue[] {
  if (row === null) return [];
  const values: RecordValue[] = [];
  for (const field of fields) {
    // Only extracted fields; the name already has its own row
    if (field.role !== "extracted" || field.is_record_name) continue;
    const cell = row.cells.find((item) => item.field === field.key);
    const shown = cell?.display_value ?? cell?.value ?? null;
    if (cell === undefined || cell.is_placeholder || shown === null || shown.length === 0) continue;
    values.push({ column: field.column, value: shown });
  }
  return values;
}
