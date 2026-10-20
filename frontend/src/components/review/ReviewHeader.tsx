// The Review screen header (UI_SPEC §4.3): run state, run name with rename (PATCH /runs/{id}),
// document count, lookup list version and reference data version.
import { useState, type FormEvent } from "react";
import { useApiClient } from "../../api/client";
import { describeError } from "../../api/errors";
import { renameRun } from "../../api/review";
import type { RunDetail } from "../../api/types";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";
import "./ReviewHeader.css";

// The longest run name the API takes (RenameRunRequest maxLength)
const MAX_NAME_LENGTH = 200;

/** Props of the header: the run, the run's lookup list version, and what a rename gives back. */
interface ReviewHeaderProps {
  run: RunDetail;
  lookupListsVersion: string;
  onRenamed: (run: RunDetail) => void;
}

/** Show the run's name and versions; the pencil button opens the rename form. */
export function ReviewHeader({ run, lookupListsVersion, onRenamed }: ReviewHeaderProps) {
  const [isRenaming, setIsRenaming] = useState(false);
  const documentCount = run.documents.length;
  const meta = [
    `${documentCount} ${documentCount === 1 ? "document" : "documents"}`,
    `Lookup lists ${lookupListsVersion}`,
    `Reference data ${run.reference_data_version ?? "none"}`,
  ];
  const state = run.is_verified ? `Verified by ${run.verified_by ?? "a reviewer"}` : "In review";
  return (
    <div className="review-header page-heading">
      <div className="eyebrow">Run · {state}</div>
      {isRenaming ? (
        <RenameForm run={run} onCancel={() => setIsRenaming(false)} onRenamed={(renamed) => { setIsRenaming(false); onRenamed(renamed); }} />
      ) : (
        <div className="review-header__title-row">
          <h1 className="review-header__title">{run.name}</h1>
          <button type="button" className="icon-button" aria-label="Rename run" onClick={() => setIsRenaming(true)}>
            <Icon name="pencil" />
          </button>
        </div>
      )}
      <div className="review-header__meta">{meta.join(" · ")}</div>
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
    <form className="review-header__rename" onSubmit={handleSubmit}>
      <label htmlFor="rename-run" className="visually-hidden">Run name</label>
      <input
        id="rename-run"
        className="review-header__input"
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
