// Undo of bulk actions in the bottom bar (UI_SPEC §4.3 "Each bulk action is one undo"), from
// the API's bulk action list: the newest undoable one with its Undo button, and the earlier
// undoable ones under "Earlier bulk actions". Undo sends one undo_bulk change, then re-checks.
import { useState } from "react";
import type { BulkActionSummary, ReviewView, RunField } from "../../api/types";
import { describeBulkAction } from "../../lib/bulkActions";
import { formatStarted } from "../../lib/format";
import { useBulkActions } from "../../lib/useBulkActions";
import type { ReviewSession } from "../../lib/useReviewSession";
import { ErrorMessage } from "../ErrorMessage";

/** Props of the undo note: the run, its view and fields, and the session. */
interface UndoBulkProps {
  runId: string;
  view: ReviewView;
  fields: RunField[];
  session: ReviewSession;
}

/** Show the bulk actions that can still be undone (nothing when there are none). */
export function UndoBulk({ runId, view, fields, session }: UndoBulkProps) {
  const bulk = useBulkActions(runId, view, session.hasPendingChanges);
  const [hasFailed, setHasFailed] = useState(false);
  const undoable = bulk.actions.filter((action) => action.can_undo);
  const columnOf = (field: string) => fields.find((item) => item.key === field)?.column ?? field;

  // Undo the whole bulk action in one change, read the list again, then re-check
  const undo = async (action: BulkActionSummary) => {
    setHasFailed(false);
    if (!(await session.submitChanges([{ type: "undo_bulk", bulk_id: action.bulk_id }]))) {
      setHasFailed(true);
      return;
    }
    await bulk.reload();
    await session.recheckNow();
  };

  if (undoable.length === 0) {
    return bulk.errorMessage !== null ? <ErrorMessage message={bulk.errorMessage} /> : null;
  }
  const [latest, ...earlier] = undoable;
  return (
    <div className="action-bar__undo" role="status">
      <UndoItem action={latest} prefix="Last bulk action: " columnOf={columnOf} isBusy={session.isBusy} onUndo={undo} />
      {earlier.length > 0 && (
        <details className="action-bar__undo-earlier">
          <summary>Earlier bulk actions you can undo ({earlier.length})</summary>
          <ul>
            {earlier.map((action) => (
              <li key={action.bulk_id}>
                <UndoItem action={action} prefix="" columnOf={columnOf} isBusy={session.isBusy} onUndo={undo} />
              </li>
            ))}
          </ul>
        </details>
      )}
      {hasFailed && session.saveError !== null && <ErrorMessage message={session.saveError} />}
      {bulk.errorMessage !== null && <ErrorMessage message={bulk.errorMessage} />}
    </div>
  );
}

/** Props of one undoable bulk action. */
interface UndoItemProps {
  action: BulkActionSummary;
  prefix: string;
  columnOf: (field: string) => string;
  isBusy: boolean;
  onUndo: (action: BulkActionSummary) => Promise<void>;
}

/** One bulk action: what it did, who did it and when, and its Undo button. */
function UndoItem({ action, prefix, columnOf, isBusy, onUndo }: UndoItemProps) {
  const description = describeBulkAction(action, columnOf);
  return (
    <span className="action-bar__undo-item">
      <span>
        {prefix}
        {description} · {action.created_by}, {formatStarted(action.created_at)}
      </span>
      <button type="button" className="button-text" aria-label={`Undo: ${description}`} disabled={isBusy} onClick={() => void onUndo(action)}>
        Undo
      </button>
    </span>
  );
}
