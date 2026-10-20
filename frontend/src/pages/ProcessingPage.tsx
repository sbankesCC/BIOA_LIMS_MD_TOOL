// The Processing screen (UI_SPEC §4.2): the step list while a run is processed, the reason
// and Retry when it failed, and a finished state once the run is ready for review.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { retryRun } from "../api/runs";
import type { RunDetail } from "../api/types";
import { ErrorMessage } from "../components/ErrorMessage";
import { Icon } from "../components/Icon";
import { StepList } from "../components/StepList";
import { formatStarted } from "../lib/format";
import { isProcessing } from "../lib/processingSteps";
import { DEFAULT_POLL_INTERVAL_MS, useRunPolling } from "../lib/useRunPolling";
import "./ProcessingPage.css";

// Shown when a failed run has no error issue that explains why
const FALLBACK_FAILURE_REASON =
  "The run stopped before it finished. Retry the run; if it fails again, contact support.";

/** Props of the screen: the run to show and, in tests, a shorter poll interval. */
interface ProcessingPageProps {
  runId: string;
  pollIntervalMs?: number;
}

/** Show one run's processing progress, failure or completion. */
export function ProcessingPage({ runId, pollIntervalMs = DEFAULT_POLL_INTERVAL_MS }: ProcessingPageProps) {
  const { run, errorMessage, reload } = useRunPolling(runId, pollIntervalMs);

  // Before the first answer: an error with Try again, or a loading line
  if (run === null) {
    return (
      <main className="page">
        {errorMessage !== null ? (
          <LoadError message={errorMessage} onRetry={reload} />
        ) : (
          <p className="muted">Loading the run…</p>
        )}
      </main>
    );
  }
  return (
    <main className="page processing">
      <RunHeading run={run} />
      {errorMessage !== null && <LoadError message={errorMessage} onRetry={reload} />}
      {run.status === "failed" ? <FailedCard run={run} /> : <ProgressCard run={run} />}
    </main>
  );
}

/** Show a loading error with a button to load again. */
function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="processing__load-error">
      <ErrorMessage message={message} />
      <button type="button" className="button-secondary" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

/** Return the eyebrow text for a run: in progress, failed or ready. */
function describeRunState(run: RunDetail): string {
  if (run.status === "failed") return "Run · Failed";
  return isProcessing(run.status) ? "Run · In progress" : "Run · Ready";
}

/** The heading: state, run name, when it started, documents and data versions. */
function RunHeading({ run }: { run: RunDetail }) {
  const documentCount = run.documents.length;
  const metaParts = [
    `Started ${formatStarted(run.created_at)}`,
    `${documentCount} ${documentCount === 1 ? "document" : "documents"}`,
    `Lookup lists ${run.config_versions.lookup_lists}`,
    `Reference data ${run.reference_data_version ?? "none"}`,
  ];
  // A retried run names the failed run it came from
  if (run.retry_of !== null && run.retry_of !== undefined) {
    metaParts.push(`Retry of ${run.retry_of}`);
  }
  return (
    <div className="processing__heading">
      <div className="page-heading">
        <div className="eyebrow">{describeRunState(run)}</div>
        <h1 className="processing__title">{run.name}</h1>
        <div className="processing__meta">{metaParts.join(" · ")}</div>
      </div>
      <Link to="/runs" className="processing__back">
        Back to runs
      </Link>
    </div>
  );
}

/** The step list while processing, or every step checked once the run is ready. */
function ProgressCard({ run }: { run: RunDetail }) {
  const isRunning = isProcessing(run.status);
  return (
    <section className="card processing__card" aria-labelledby="progress-heading">
      <h2 id="progress-heading">
        {isRunning ? "Working on your documents" : "Your run is ready for review"}
      </h2>
      {/* Screen readers hear the step changes as they happen */}
      <div aria-live="polite">
        <StepList status={run.status} />
      </div>
      <div className="processing__note">
        <Icon name="save" size={20} />
        <div>
          {isRunning ? (
            <>
              You can leave this page. Your run is saved, and it will be under <strong>Runs</strong>{" "}
              when it's ready.
            </>
          ) : (
            "Extraction is finished. The records are saved and ready for review."
          )}
        </div>
      </div>
      {/* A run in review opens on the Review screen */}
      {!isRunning && (
        <div>
          <Link to={`/runs/${run.run_id}/review`} className="button-main processing__review-link">
            Review the records
            <Icon name="arrow-right" size={20} />
          </Link>
        </div>
      )}
    </section>
  );
}

/** The failed state: why the run failed, and Retry, which starts a new run from the same files. */
function FailedCard({ run }: { run: RunDetail }) {
  const client = useApiClient();
  const navigate = useNavigate();
  const [retryError, setRetryError] = useState<string | null>(null);
  const [isRetrying, setIsRetrying] = useState(false);
  const reasons = findFailureReasons(run);

  // Start the new run and open it; the failed run stays in the list
  const handleRetry = async () => {
    setIsRetrying(true);
    setRetryError(null);
    try {
      const started = await retryRun(client, run.run_id);
      navigate(`/runs/${started.run_id}`);
    } catch (error) {
      setRetryError(describeError(error));
      setIsRetrying(false);
    }
  };

  return (
    <section className="card processing__card" aria-labelledby="failed-heading">
      <h2 id="failed-heading" className="processing__failed-title">
        <Icon name="cross-circle" size={22} />
        This run could not be finished
      </h2>
      <ul className="processing__reasons">
        {reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {retryError !== null && <ErrorMessage message={retryError} />}
      <div className="processing__retry">
        <button type="button" className="button-main" onClick={handleRetry} disabled={isRetrying}>
          {isRetrying ? "Starting…" : "Retry"}
        </button>
        <span className="muted">
          Retry starts a new run from the same files. This run stays in the list.
        </span>
      </div>
    </section>
  );
}

/** Return the messages of the run's open error issues, or a plain fallback reason. */
function findFailureReasons(run: RunDetail): string[] {
  const reasons = run.run_issues
    .filter((issue) => issue.severity === "error" && issue.status !== "resolved")
    .map((issue) => issue.message);
  return reasons.length > 0 ? reasons : [FALLBACK_FAILURE_REASON];
}
