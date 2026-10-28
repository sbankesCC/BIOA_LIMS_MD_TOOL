// A modal dialog in the style of the mockups (white card over a dimmed page): a title, an X,
// the content and a row of buttons. Escape and the X close it. Used by the M13 dialogs.
import { useEffect, useId, useRef, type ReactNode } from "react";
import { Icon } from "./Icon";
import "./Dialog.css";

/** Props of a dialog: its title, content, buttons and what closing does. */
interface DialogProps {
  title: string;
  children: ReactNode;
  actions: ReactNode;
  onClose: () => void;
}

/** Show a modal dialog; focus moves to its X when it opens. */
export function Dialog({ title, children, actions, onClose }: DialogProps) {
  const titleId = useId();
  const closeButton = useRef<HTMLButtonElement>(null);

  // Focus the X on open, and close on Escape
  useEffect(() => {
    closeButton.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="dialog__backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="dialog__header">
          <h2 id={titleId} className="dialog__title">{title}</h2>
          <button ref={closeButton} type="button" className="icon-button" aria-label="Close dialog" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="dialog__body">{children}</div>
        <div className="dialog__actions">{actions}</div>
      </div>
    </div>
  );
}
