// The Review screen's bottom action bar (UI_SPEC §4.3): progress (issues resolved), the
// production reminder, the verified state, "Verify output" and "Export to Excel" (gold, always
// enabled), Undo of bulk actions, and the post-export state with both downloads (§4.5).
import { useState } from "react";
import type { ReviewView, RunDetail } from "../../api/types";
import { formatDay } from "../../lib/format";
import { useRunExport } from "../../lib/useRunExport";
import type { BottomBarContext } from "../../pages/ReviewPage";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";
import { ExportDownloads } from "./ExportDownloads";
import { PRODUCTION_REMINDER } from "./reviewText";
import { UndoBulk } from "./UndoBulk";
import { VerifyDialog } from "./VerifyDialog";
import "./ActionBar.css";

/** Show the bottom bar with its actions, and the Verify dialog when it is open. */
export function ActionBar(props: BottomBarContext) {
  const { run, view, fields, session, reload } = props;
  const [isVerifyOpen, setIsVerifyOpen] = useState(false);
  const exporting = useRunExport(run.run_id, session, props.refreshRun);

  // Saved changes are re-checked first, so the dialog counts what is really open
  const openVerify = async () => {
    if (session.hasPendingChanges) await session.recheckNow();
    setIsVerifyOpen(true);
  };

  return (
    <section className="action-bar" aria-label="Review actions">
      <UndoBulk runId={run.run_id} view={view} fields={fields} session={session} />
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

/** Progress: issues resolved of all red and yellow issues (UI_SPEC §4.3, from the API's counts). */
function Progress({ view }: { view: ReviewView }) {
  const { resolved_issues: resolved, total_issues: total } = view.counts;
  const percent = total > 0 ? Math.round((resolved / total) * 100) : 100;
  return (
    <div className="action-bar__progress">
      <div className="action-bar__progress-text">
        Issues resolved: {resolved} of {total}
      </div>
      <div className="action-bar__track" role="progressbar" aria-label="Issues resolved" aria-valuemin={0} aria-valuemax={total} aria-valuenow={resolved}>
        <div className="action-bar__fill" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
