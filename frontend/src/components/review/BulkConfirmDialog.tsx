// The bulk-action confirmation list (UI_SPEC §4.3, §5): every record the bulk preview matched,
// all checked; the user may uncheck any. Confirming sends one change list with one bulk_id,
// then re-checks the run. A missing value without an issue needs a reason (CONTRACTS §6).
import { useState } from "react";
import type { BulkPreview, BulkPreviewMatch } from "../../api/types";
import { buildBulkChanges, describeOfferTitle, makeMatchKey, needsReason, type BulkOffer } from "../../lib/bulkActions";
import { makeBulkId } from "../../lib/ids";
import type { ReviewSession } from "../../lib/useReviewSession";
import { Dialog } from "../Dialog";
import { ErrorMessage } from "../ErrorMessage";

/** A bulk action that was saved: its ID (for Undo), what it did and how many changes it sent. */
export interface SavedBulk {
  bulkId: string;
  description: string;
  count: number;
}

/** Props of the dialog: the preview, the offer, the session and what closing or saving does. */
interface BulkConfirmDialogProps {
  preview: BulkPreview;
  offer: BulkOffer;
  shortLabel: string;
  session: ReviewSession;
  onClose: () => void;
  onSaved: (bulk: SavedBulk) => void;
}

/** Show the confirmation list and send the bulk change when the user confirms. */
export function BulkConfirmDialog({ preview, offer, shortLabel, session, onClose, onSaved }: BulkConfirmDialogProps) {
  const [checkedKeys, setCheckedKeys] = useState<ReadonlySet<string>>(() => new Set(preview.matches.map(makeMatchKey)));
  const [reason, setReason] = useState("");
  const [hasFailed, setHasFailed] = useState(false);
  const checked = preview.matches.filter((match) => checkedKeys.has(makeMatchKey(match)));
  const isReasonNeeded = needsReason(offer, checked);
  const isReady = checked.length > 0 && (!isReasonNeeded || reason.trim().length > 0);
  const title = describeOfferTitle(offer, shortLabel);

  // Check or uncheck one record
  const toggle = (key: string) => {
    setCheckedKeys((keys) => {
      const next = new Set(keys);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Send every checked record's change with one new bulk ID, then re-check the run
  const confirm = async () => {
    const bulkId = makeBulkId();
    const trimmed = reason.trim();
    const changes = buildBulkChanges(offer, preview.field, checked, bulkId, trimmed.length > 0 ? trimmed : null);
    setHasFailed(false);
    if (!(await session.submitChanges(changes))) {
      setHasFailed(true);
      return;
    }
    onSaved({ bulkId, description: `${title} (${changes.length} ${changes.length === 1 ? "change" : "changes"})`, count: changes.length });
    await session.recheckNow();
  };

  return (
    <Dialog
      title={title}
      onClose={onClose}
      actions={
        <>
          <button type="button" className="button-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="dialog__primary" disabled={!isReady || session.isBusy} onClick={() => void confirm()}>
            {session.isBusy ? "Working…" : `Apply to ${checked.length} ${checked.length === 1 ? "record" : "records"}`}
          </button>
        </>
      }
    >
      <p className="bulk-confirm__count" aria-live="polite">
        {checked.length} of {preview.count} selected. Uncheck any record you want to leave as it is.
      </p>
      <ul className="bulk-confirm__list" aria-label="Records this action changes">
        {preview.matches.map((match) => (
          <MatchItem key={makeMatchKey(match)} match={match} isChecked={checkedKeys.has(makeMatchKey(match))} onToggle={() => toggle(makeMatchKey(match))} />
        ))}
      </ul>
      {isReasonNeeded && (
        <label className="dialog__text">
          Reason (required: some of these values have no open issue)
          <textarea rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
        </label>
      )}
      <p className="dialog__hint">This is one action: you can undo it in one step.</p>
      {hasFailed && session.saveError !== null && <ErrorMessage message={session.saveError} />}
    </Dialog>
  );
}

/** One record of the list: a checkbox with the record's name and its current value. */
function MatchItem({ match, isChecked, onToggle }: { match: BulkPreviewMatch; isChecked: boolean; onToggle: () => void }) {
  return (
    <li>
      <label className="bulk-confirm__item">
        <input type="checkbox" checked={isChecked} onChange={onToggle} />
        <span>
          <strong>{match.name ?? match.record_id}</strong>
          <span className="muted"> · now: {match.value !== null && match.value.length > 0 ? match.value : "— (no value)"}</span>
        </span>
      </label>
    </li>
  );
}
