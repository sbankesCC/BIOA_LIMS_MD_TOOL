// Exclude and restore a record (UI_SPEC §4.3): "Exclude record" in the panel footer asks for a
// required reason; "Restore" on an excluded row (and in the footer) brings it back. Each sends
// one change and then re-checks the run, as UI_SPEC "Saving and re-checking" says.
import { useState } from "react";
import type { ReviewRow } from "../../api/types";
import type { NewChange } from "../../lib/issueActions";
import type { ReviewSession } from "../../lib/useReviewSession";
import { Dialog } from "../Dialog";
import { ErrorMessage } from "../ErrorMessage";

/** Send one change and re-check the run; returns true when the change was stored. */
async function saveAndRecheck(session: ReviewSession, change: NewChange): Promise<boolean> {
  if (!(await session.submitChanges([change]))) return false;
  await session.recheckNow();
  return true;
}

/** The panel footer's left side: Exclude record, or Restore record for an excluded one. */
export function RecordExclusionAction({ row, session }: { row: ReviewRow | null; session: ReviewSession }) {
  const [isAsking, setIsAsking] = useState(false);
  if (row === null) return null;
  if (row.exclusion !== null) {
    return <RestoreButton row={row} session={session} label="Restore record" />;
  }
  return (
    <>
      <button type="button" className="panel__exclude" disabled={session.isBusy} onClick={() => setIsAsking(true)}>
        Exclude record
      </button>
      {isAsking && <ExcludeDialog row={row} session={session} onClose={() => setIsAsking(false)} />}
    </>
  );
}

/** Ask for the reason, then exclude the record. */
function ExcludeDialog({ row, session, onClose }: { row: ReviewRow; session: ReviewSession; onClose: () => void }) {
  const [reason, setReason] = useState("");
  const [hasFailed, setHasFailed] = useState(false);
  const trimmed = reason.trim();

  // Send exclude_record with the reason; close once it is stored
  const exclude = async () => {
    setHasFailed(false);
    const change: NewChange = { type: "exclude_record", record_id: row.record_id, reason: trimmed };
    if (await saveAndRecheck(session, change)) onClose();
    else setHasFailed(true);
  };

  return (
    <Dialog
      title="Exclude record"
      onClose={onClose}
      actions={
        <>
          <button type="button" className="button-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="dialog__primary" disabled={trimmed.length === 0 || session.isBusy} onClick={() => void exclude()}>
            {session.isBusy ? "Working…" : "Exclude record"}
          </button>
        </>
      }
    >
      <p>
        <strong>{row.name ?? "This record"}</strong> will be left out of the export. You can restore it later.
      </p>
      <label className="dialog__text">
        Reason (required)
        <textarea rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      {trimmed.length === 0 && <p className="dialog__hint">Add a reason to exclude the record.</p>}
      {hasFailed && session.saveError !== null && <ErrorMessage message={session.saveError} />}
    </Dialog>
  );
}

/** Restore an excluded record (a text button), with the API's message if it is refused. */
export function RestoreButton({ row, session, label = "Restore" }: { row: ReviewRow; session: ReviewSession; label?: string }) {
  const [hasFailed, setHasFailed] = useState(false);

  // Send restore_record, then re-check
  const restore = async () => {
    setHasFailed(false);
    if (!(await saveAndRecheck(session, { type: "restore_record", record_id: row.record_id }))) setHasFailed(true);
  };

  return (
    <>
      {" "}
      <button type="button" className="button-text" disabled={session.isBusy} aria-label={`${label}: ${row.name ?? row.record_id}`} onClick={() => void restore()}>
        {label}
      </button>
      {hasFailed && session.saveError !== null && <ErrorMessage message={session.saveError} />}
    </>
  );
}
