// The Review screen's bottom action bar (UI_SPEC §4.3): progress, the production reminder, the
// verified state, "Verify output" and "Export to Excel" (gold, always enabled), the Undo of the
// last bulk action, and the post-export state with the loader and audit downloads (§4.5).
import { useState } from "react";
import type { ReviewView, RunDetail } from "../../api/types";
import { formatDay } from "../../lib/format";
import { useRunExport } from "../../lib/useRunExport";
import type { BottomBarContext } from "../../pages/ReviewPage";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";
import type { SavedBulk } from "./BulkConfirmDialog";
import { ExportDownloads } from "./ExportDownloads";
import { PRODUCTION_REMINDER } from "./reviewText";
import { VerifyDialog } from "./VerifyDialog";
import "./ActionBar.css";

/** Props of the bar: the screen's context, the last bulk action and what an undo does. */
interface ActionBarProps extends BottomBarContext {
  lastBulk: SavedBulk | null;
  onBulkUndone: () => void;
}

/** Show the bottom bar with its actions, and the Verify dialog when it is open. */
export function ActionBar(props: ActionBarProps) {
  const { run, view, session, reload } = props;
  const [isVerifyOpen, setIsVerifyOpen] = useState(false);
  const exporting = useRunExport(run.run_id, session, props.refreshRun);

  // Saved changes are re-checked first, so the dialog counts what is really open
  const openVerify = async () => {
    if (session.hasPendingChanges) await session.recheckNow();
    setIsVerifyOpen(true);
  };

  return (
    <section className="action-bar" aria-label="Review actions">
      {props.lastBulk !== null && <UndoNote {...props} lastBulk={props.lastBulk} />}
      <div className="action-bar__main">
        <div className="action-bar__info">
          <Progress view={view} />
          <p className="action-bar__reminder">
            <Icon name="info" />
            <span>{PRODUCTION_REMINDER}</span>
          </p>
        </div>
        <div className="action-bar__buttons">
          <span className="action-bar__state">{describeVerifiedState(run)}</span>
          <button type="button" className="button-secondary" disabled={session.isBusy} onClick={() => void openVerify()}>
            Verify output
          </button>
          <button type="button" className="button-main" disabled={exporting.isExporting} onClick={() => void exporting.exportRun()}>
            <Icon name="download" />
            {exporting.isExporting ? "Exporting…" : "Export to Excel"}
          </button>
        </div>
      </div>
      {exporting.errorMessage !== null && <ErrorMessage message={exporting.errorMessage} />}
      <ExportDownloads runId={run.run_id} latest={exporting.latest} exports={run.exports} />
      {isVerifyOpen && <VerifyDialog run={run} view={view} session={session} reload={reload} onClose={() => setIsVerifyOpen(false)} />}
    </section>
  );
}

/** Return the verified state text: who verified it and when, or the draft note. */
export function describeVerifiedState(run: RunDetail): string {
  if (!run.is_verified) return "Not verified yet: exports are saved as drafts";
  const day = run.verified_at !== null ? ` on ${formatDay(new Date(run.verified_at))}` : "";
  return `Verified by ${run.verified_by ?? "a reviewer"}${day}`;
}

/** Progress: records with nothing left to do, and the open issue counts. */
function Progress({ view }: { view: ReviewView }) {
  const included = view.rows.filter((row) => row.exclusion === null);
  const ready = included.filter((row) => row.action_needed === "none").length;
  const percent = included.length > 0 ? Math.round((ready / included.length) * 100) : 100;
  const { open_errors: errors, open_warnings: warnings } = view.counts;
  return (
    <div className="action-bar__progress">
      <div className="action-bar__progress-text">
        Records ready: {ready} of {included.length} · Open issues: {errors} to fix, {warnings} {warnings === 1 ? "warning" : "warnings"}
      </div>
      <div className="action-bar__track" role="progressbar" aria-label="Records ready" aria-valuemin={0} aria-valuemax={included.length} aria-valuenow={ready}>
        <div className="action-bar__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

/** "Last bulk action: … Undo": undoing sends one undo_bulk change, then re-checks. */
function UndoNote({ session, lastBulk, onBulkUndone }: ActionBarProps & { lastBulk: SavedBulk }) {
  const [hasFailed, setHasFailed] = useState(false);

  // Undo the whole bulk action in one change
  const undo = async () => {
    setHasFailed(false);
    if (!(await session.submitChanges([{ type: "undo_bulk", bulk_id: lastBulk.bulkId }]))) {
      setHasFailed(true);
      return;
    }
    onBulkUndone();
    await session.recheckNow();
  };

  return (
    <div className="action-bar__undo" role="status">
      <span>Last bulk action: {lastBulk.description}.</span>
      <button type="button" className="button-text" disabled={session.isBusy} onClick={() => void undo()}>
        Undo
      </button>
      {hasFailed && session.saveError !== null && <ErrorMessage message={session.saveError} />}
    </div>
  );
}
