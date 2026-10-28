// Checks a typed or picked value against its field's rules from GET /runs/{run_id}/fields
// (length, number type, allowed values) before it is saved. Validation checks again later.
import type { RunField } from "../api/types";

// Whole numbers and decimal numbers as the loader takes them
const INTEGER_PATTERN = /^-?\d+$/;
const DECIMAL_PATTERN = /^-?\d+(\.\d+)?$/;

/** Return a plain message when the value breaks a field rule, or null when it is fine. */
export function checkValue(field: RunField, text: string): string | null {
  const value = text.trim();
  if (value.length === 0) {
    return "Enter a value.";
  }
  // List and Y/N fields take only their allowed values
  if (field.allowed_values.length > 0 && !field.allowed_values.includes(value)) {
    return `Pick a value from the ${field.column} list.`;
  }
  if (field.max_length !== null && value.length > field.max_length) {
    return `${field.column} can be at most ${field.max_length} characters (this is ${value.length}).`;
  }
  if (field.type === "integer" && !INTEGER_PATTERN.test(value)) {
    return `${field.column} must be a whole number, such as 10.`;
  }
  if (field.type === "decimal" && !DECIMAL_PATTERN.test(value)) {
    return `${field.column} must be a number, such as 2.5.`;
  }
  return null;
}
