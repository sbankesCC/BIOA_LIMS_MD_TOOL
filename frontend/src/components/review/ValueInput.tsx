// The value input of an issue action (UI_SPEC §4.3): a searchable dropdown for list and Y/N
// fields, or a checked text box for free text (length and number rules from the field).
import { useId } from "react";
import type { RunField } from "../../api/types";
import { checkValue } from "../../lib/valueCheck";
import { SearchableDropdown } from "./SearchableDropdown";

/** Props of the input: the field, the current text, a hint for ordering, and the change handler. */
interface ValueInputProps {
  field: RunField;
  value: string;
  hint?: string | null;
  label?: string;
  onChange: (value: string, problem: string | null) => void;
}

/** Show the right input for a field and report each value with its problem (or null). */
export function ValueInput({ field, value, hint = null, label, onChange }: ValueInputProps) {
  const inputId = useId();
  const problem = value.length > 0 ? checkValue(field, value) : null;
  const report = (text: string) => onChange(text, checkValue(field, text));

  // List and Y/N fields: pick from the allowed values only
  if (field.allowed_values.length > 0) {
    return (
      <SearchableDropdown
        label={label ?? field.column}
        options={field.allowed_values}
        value={value}
        hint={hint}
        onChange={report}
      />
    );
  }
  // Free text: a text box checked as the user types
  return (
    <div className="value-input">
      <label htmlFor={inputId} className="dropdown__label">
        {label ?? field.column}
      </label>
      <input
        id={inputId}
        type="text"
        className="dropdown__input"
        value={value}
        aria-invalid={problem !== null}
        aria-describedby={problem !== null ? `${inputId}-problem` : undefined}
        onChange={(event) => report(event.target.value)}
      />
      {problem !== null && (
        <div id={`${inputId}-problem`} className="value-input__problem">
          {problem}
        </div>
      )}
    </div>
  );
}
