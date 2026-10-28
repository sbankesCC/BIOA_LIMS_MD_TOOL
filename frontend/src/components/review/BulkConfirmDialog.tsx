// The bulk-action confirmation list (UI_SPEC §4.3, §5): every record the bulk preview matched,
// all checked; the user may uncheck any. Confirming sends one change list with one bulk_id,
// then re-checks the run. A missing value without an issue needs a reason (CONTRACTS §6).
// From "Also apply to N similar" the current record is always included (its own change, as the
// user made it), only the other records are listed, and the panel then moves to the next issue.
import { useState } from "react";
import type { BulkPreview, BulkPreviewMatch } from "../../api/types";
import { buildAlsoApplyChanges, buildBulkChanges, describeOfferTitle, isSelectedMatch, makeMatchKey, needsReason, type BulkOffer } from "../../lib/bulkActions";
import type { NewChange } from "../../lib/issueActions";
import { makeBulkId } from "../../lib/ids";
import type { ReviewSession } from "../../lib/useReviewSession";
import { Dialog } from "../Dialog";
import { ErrorMessage } from "../ErrorMessage";

/**
 * Props of the dialog: the preview, the offer, the session and what closing or saving does.
 * `currentChange` is the current record's own change from "Also apply" (null for a plain bulk action).
 */
interface BulkConfirmDialogProps {
  preview: BulkPreview;
  offer: BulkOffer;
  shortLabel: string;
  session: ReviewSession;
  currentChange: NewChange | null;
  onClose: () => void;
  onSaved: () => void;
}

/** Show the confirmation list and send the bulk change when the user confirms. */
export function BulkConfirmDialog({ preview, offer, shortLabel, session, currentChange, onClose, onSaved }: BulkConfirmDialogProps) {
  const isAlsoApply = currentChange !== null;
  // "Also apply" lists only the other records; the current one is always part of the change
  const listed = isAlsoApply ? preview.matches.filter((match) => !isSelectedMatch(offer, match)) : preview.matches;
  const [checkedKeys, setCheckedKeys] = useState<ReadonlySet<string>>(() => new Set(listed.map(makeMatchKey)));
  const [reason, setReason] = useState("");
  const [hasFailed, setHasFailed] = useState(false);
  const checked = listed.filter((match) => checkedKeys.has(makeMatchKey(match)));
  const isReasonNeeded = needsReason(offer, checked);
  const isReady = (isAlsoApply || checked.length > 0) && (!isReasonNeeded || reason.trim().length > 0);
  const recordCount = checked.length + (isAlsoApply ? 1 : 0);
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

  // Send every change with one new bulk ID, then re-check (and, from "Also apply", move on)
  const confirm = async () => {
    const bulkId = makeBulkId();
    const trimmed = reason.trim();
    const reasonOrNull = trimmed.length > 0 ? trimmed : null;
    setHasFailed(false);
    if (currentChange !== null) {
      const changes = buildAlsoApplyChanges(offer, preview.field, currentChange, checked, bulkId, reasonOrNull);
      if (await session.saveBulkAndNext(changes)) onSaved();
      else setHasFailed(true);
      return;
    }
    const changes = buildBulkChanges(offer, preview.field, checked, bulkId, reasonOrNull);
    if (!(await session.submitChanges(changes))) {
      setHasFailed(true);
      return;
    }
    onSaved();
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
            {session.isBusy ? "Working…" : `Apply to ${recordCount} ${recordCount === 1 ? "record" : "records"}`}
          </button>
        </>
      }
    >
      {isAlsoApply && <p className="bulk-confirm__current">This record is always included.</p>}
      <p className="bulk-confirm__count" aria-live="polite">
        {`${checked.length} of ${listed.length}${isAlsoApply ? " other records" : ""} selected.`} Uncheck any record you want to leave as it is.
      </p>
      <ul className="bulk-confirm__list" aria-label="Records this action changes">
        {listed.map((match) => (
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
