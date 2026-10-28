// A searchable dropdown (combobox) for list and Y/N fields: typing filters the options and
// orders them closest first; before typing, a hint (the value as written) orders them.
// Keyboard: arrows move, Enter picks, Escape closes. Options come from GET /runs/{id}/fields.
import { useId, useMemo, useState, type KeyboardEvent } from "react";
import { rankOptions } from "../../lib/optionRanking";
import "./SearchableDropdown.css";

/** Props of the dropdown: its label, options, picked value, hint text and change handler. */
interface SearchableDropdownProps {
  label: string;
  options: string[];
  value: string;
  hint?: string | null;
  placeholder?: string;
  onChange: (value: string) => void;
}

/** Show a text box that filters a list of options, with the closest matches first. */
export function SearchableDropdown({ label, options, value, hint = null, placeholder, onChange }: SearchableDropdownProps) {
  const baseId = useId();
  const listId = `${baseId}-list`;
  const [query, setQuery] = useState(value);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  // Typed text filters; untouched text (the picked value) only orders by the hint
  const isTyped = query !== value;
  const shown = useMemo(
    () => (isTyped ? rankOptions(options, query, true) : rankOptions(options, hint ?? "", false)),
    [options, query, hint, isTyped],
  );

  // Pick an option: show it in the box and tell the parent
  const pick = (option: string) => {
    setQuery(option);
    setIsOpen(false);
    onChange(option);
  };

  // Typing opens the list at its first (closest) option
  const handleType = (text: string) => {
    setQuery(text);
    setIsOpen(true);
    setActiveIndex(0);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    // Arrows open the list and move through it
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActiveIndex((index) => (isOpen ? Math.min(Math.max(index + step, 0), shown.length - 1) : 0));
      setIsOpen(true);
      return;
    }
    // Enter picks the highlighted option; Escape closes the list
    if (event.key === "Enter" && isOpen && shown[activeIndex] !== undefined) {
      event.preventDefault();
      pick(shown[activeIndex]);
    } else if (event.key === "Escape" && isOpen) {
      event.preventDefault();
      setIsOpen(false);
    }
  };

  const activeId = isOpen && shown[activeIndex] !== undefined ? `${baseId}-option-${activeIndex}` : undefined;
  return (
    <div className="dropdown">
      <label htmlFor={`${baseId}-input`} className="dropdown__label">
        {label}
      </label>
      <input
        id={`${baseId}-input`}
        className="dropdown__input"
        type="text"
        role="combobox"
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={isOpen}
        aria-controls={listId}
        aria-activedescendant={activeId}
        placeholder={placeholder ?? `Search the ${label} list…`}
        value={query}
        onChange={(event) => handleType(event.target.value)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        onKeyDown={handleKeyDown}
      />
      {isOpen && (
        <ul id={listId} role="listbox" aria-label={`${label} options`} className="dropdown__list">
          {shown.length === 0 && <li className="dropdown__empty">No list value matches. Try other words.</li>}
          {shown.map((option, index) => (
            <li
              key={option}
              id={`${baseId}-option-${index}`}
              role="option"
              aria-selected={option === value}
              className={index === activeIndex ? "dropdown__option dropdown__option--active" : "dropdown__option"}
              // Mouse down (not click) so the box does not lose focus and close the list first
              onMouseDown={(event) => {
                event.preventDefault();
                pick(option);
              }}
            >
              {option}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
