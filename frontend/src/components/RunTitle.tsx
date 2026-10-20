// The run name heading with its rename pencil (UI_SPEC §4.1 "editable now and later"), shared by
// the Processing and Review screens. A rename is sent as PATCH /runs/{id}.
import { useState, type FormEvent } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { renameRun } from "../api/review";
import type { RunDetail } from "../api/types";
import { ErrorMessage } from "./ErrorMessage";
import { Icon } from "./Icon";
import "./RunTitle.css";

// The longest run name the API takes (RenameRunRequest maxLength)
const MAX_NAME_LENGTH = 200;

/** Props of the title: the run, and what to do with the renamed run the API gives back. */
interface RunTitleProps {
  run: RunDetail;
  onRenamed: (run: RunDetail) => void;
}

/** Show the run name with a pencil button; the button swaps the name for the rename form. */
export function RunTitle({ run, onRenamed }: RunTitleProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  if (isRenaming) {
    return (
      <RenameForm
        run={run}
        onCancel={() => setIsRenaming(false)}
        onRenamed={(renamed) => {
          setIsRenaming(false);
          onRenamed(renamed);
        }}
      />
    );
  }
  return (
    <div className="run-title">
      <h1 className="run-title__name">{run.name}</h1>
      <button type="button" className="icon-button" aria-label="Rename run" onClick={() => setIsRenaming(true)}>
        <Icon name="pencil" />
      </button>
    </div>
  );
}

/** The rename form: a text box with Save and Cancel; Escape cancels. */
function RenameForm({ run, onCancel, onRenamed }: { run: RunDetail; onCancel: () => void; onRenamed: (run: RunDetail) => void }) {
  const client = useApiClient();
  const [name, setName] = useState(run.name);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const trimmed = name.trim();

  // Send the new name; the API answers with the updated run
  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (trimmed.length === 0) {
      setErrorMessage("Enter a run name.");
      return;
    }
    setIsSaving(true);
    try {
      onRenamed(await renameRun(client, run.run_id, trimmed));
    } catch (error) {
      setErrorMessage(describeError(error));
      setIsSaving(false);
    }
  };

  return (
    <form className="run-title__rename" onSubmit={handleSubmit}>
      <label htmlFor="rename-run" className="visually-hidden">Run name</label>
      <input
        id="rename-run"
        className="run-title__input"
        value={name}
        maxLength={MAX_NAME_LENGTH}
        autoFocus
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && onCancel()}
      />
      <button type="submit" className="button-secondary" disabled={isSaving}>
        {isSaving ? "Saving…" : "Save name"}
      </button>
      <button type="button" className="button-text" onClick={onCancel}>
        Cancel
      </button>
      {errorMessage !== null && <ErrorMessage message={errorMessage} />}
    </form>
  );
}
