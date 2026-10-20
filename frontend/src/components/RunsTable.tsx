// The runs table: name, started, status (or the "Exported · export N" badge), record count and
// what needs action, with a failed run's reason (UI_SPEC §4.1, mockup 1). Used for "Recent
// runs" on the Start screen and for the Runs page.
import { Link } from "react-router-dom";
import type { RunSummary } from "../api/types";
import { formatStarted } from "../lib/format";
import { isProcessing } from "../lib/processingSteps";
import { Icon } from "./Icon";
import { StatusBadge } from "./StatusBadge";
import "./RunsTable.css";

/** Props of the table: the runs to list, newest first. */
interface RunsTableProps {
  runs: RunSummary[];
}

/** Show runs as a table; each name opens the run. */
export function RunsTable({ runs }: RunsTableProps) {
  return (
    <div className="runs-table__scroll">
      <table className="runs-table">
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Started</th>
            <th scope="col">Status</th>
            <th scope="col">Records</th>
            <th scope="col">Needs action</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td>
                <Link to={makeRunAddress(run)} className="runs-table__name">
                  {run.name}
                </Link>
              </td>
              <td>{formatStarted(run.created_at)}</td>
              <td>
                <RunStatus run={run} />
              </td>
              <td>{hasRecords(run) ? run.counts.records : "—"}</td>
              <td>
                <NeedsAction run={run} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Return the screen a run opens on: Review once it is in review, else its progress. */
function makeRunAddress(run: RunSummary): string {
  return hasRecords(run) ? `/runs/${run.run_id}/review` : `/runs/${run.run_id}`;
}

/** Return true when the run has reached review, so its record count means something. */
function hasRecords(run: RunSummary): boolean {
  return run.status !== "failed" && !isProcessing(run.status);
}

/** Show a run in review that was exported as "Exported · export N", else its status badge. */
function RunStatus({ run }: { run: RunSummary }) {
  const latest = run.latest_export;
  if (latest === null || run.status !== "in_review") {
    return <StatusBadge status={run.status} isVerified={run.is_verified} />;
  }
  // A draft export (not verified) says so; a verified export is green
  return (
    <span className={`status-badge status-badge--${latest.is_draft ? "blue" : "green"}`}>
      <Icon name="download" size={14} strokeWidth={2.2} />
      {`Exported · export ${latest.number}${latest.is_draft ? " (draft)" : ""}`}
    </span>
  );
}

/** Show what a run needs: the failure reason and Retry, nothing while processing, else its open issues. */
function NeedsAction({ run }: { run: RunSummary }) {
  // A failed run: the API's reason, and its page has the Retry button
  if (run.status === "failed") {
    if (run.failure_reason === null) {
      return <Link to={`/runs/${run.run_id}`}>See why and retry</Link>;
    }
    return (
      <span>
        {run.failure_reason} · <Link to={`/runs/${run.run_id}`}>Retry</Link>
      </span>
    );
  }
  if (isProcessing(run.status)) {
    return <span className="muted">—</span>;
  }
  // A run in review: red issues to fix and yellow warnings, or none
  const { open_errors: toFix, open_warnings: warnings } = run.counts;
  if (toFix === 0 && warnings === 0) {
    return <span>None</span>;
  }
  return (
    <span>
      {toFix > 0 && <span className="runs-table__to-fix">{toFix} to fix</span>}
      {toFix > 0 && warnings > 0 && " · "}
      {warnings > 0 && <span>{warnings} {warnings === 1 ? "warning" : "warnings"}</span>}
    </span>
  );
}
