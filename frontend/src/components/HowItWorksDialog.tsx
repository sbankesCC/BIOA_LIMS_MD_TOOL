// The "How it works" popup: a short guide that opens on a user's first visit (UI_SPEC §3).
// Whether it was seen is remembered in localStorage; blocked storage just shows it again.
import { useCallback, useEffect, useRef, useState } from "react";
import { readStoredValue, writeStoredValue } from "../lib/storage";
import { Icon } from "./Icon";
import "./HowItWorksDialog.css";

// The localStorage key and value that mark the popup as seen
export const HOW_IT_WORKS_SEEN_KEY = "consumable-type-extractor.how-it-works-seen";
const SEEN_VALUE = "yes";

// The steps the popup explains, in order
const GUIDE_STEPS = [
  {
    title: "Upload the documents",
    text: "Add the method, study plan and any worksheets for one study (Word, PDF or Excel).",
  },
  {
    title: "The tool extracts and checks",
    text: "It finds the Consumable Types, shows where each value came from, and checks the values against the documents and the lookup lists.",
  },
  {
    title: "Review and fix",
    text: "Work through the flagged values one issue at a time. Values change only through the issue actions.",
  },
  {
    title: "Verify and export",
    text: "Verify the run, then export the Excel loader and the audit file. This tool never loads anything into LabVantage.",
  },
];

/** Hold whether the popup is open: open on the first visit, remembered once closed. */
export function useHowItWorks() {
  const [isOpen, setIsOpen] = useState(
    () => readStoredValue(HOW_IT_WORKS_SEEN_KEY) !== SEEN_VALUE,
  );
  // Closing marks the popup as seen, so it does not open by itself again
  const close = useCallback(() => {
    writeStoredValue(HOW_IT_WORKS_SEEN_KEY, SEEN_VALUE);
    setIsOpen(false);
  }, []);
  const open = useCallback(() => setIsOpen(true), []);
  return { isOpen, open, close };
}

/** Props of the popup: whether it shows and what closing does. */
interface HowItWorksDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

/** Show the "How it works" popup over the page; Escape, the X or the backdrop close it. */
export function HowItWorksDialog({ isOpen, onClose }: HowItWorksDialogProps) {
  const closeButton = useRef<HTMLButtonElement>(null);

  // Move focus into the popup when it opens, and close it on Escape
  useEffect(() => {
    if (!isOpen) {
      return;
    }
    closeButton.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }
  return (
    <div className="how-it-works__backdrop" onClick={onClose}>
      {/* Clicks inside the popup do not reach the backdrop */}
      <div
        className="how-it-works"
        role="dialog"
        aria-modal="true"
        aria-labelledby="how-it-works-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="how-it-works__header">
          <h2 id="how-it-works-title">How it works</h2>
          <button
            ref={closeButton}
            type="button"
            className="how-it-works__close"
            aria-label="Close how it works"
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </div>
        <ol className="how-it-works__steps">
          {GUIDE_STEPS.map((step, index) => (
            <li key={step.title} className="how-it-works__step">
              <span className="how-it-works__number" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <div className="how-it-works__step-title">{step.title}</div>
                <div className="muted">{step.text}</div>
              </div>
            </li>
          ))}
        </ol>
        <p className="how-it-works__note">
          Runs are saved: you can leave at any time and come back. Before importing into
          production LabVantage, review all values, including those without warnings.
        </p>
        <div className="how-it-works__footer">
          <button type="button" className="button-secondary" onClick={onClose}>
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
