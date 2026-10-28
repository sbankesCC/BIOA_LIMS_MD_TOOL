// The Review and resolve screen (UI_SPEC §4.3): header with rename, run banner, summary strip
// with filters, the read-only records grid, the source viewer and the resolution panel.
// Bulk actions, exclude/restore, Verify and export (M13) plug in through `extensions`.
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { CellSource, IssueSummary, ReviewCell, ReviewRow, ReviewView, RunDetail, RunField, SourceLocation } from "../api/types";
import { ErrorMessage } from "../components/ErrorMessage";
import { RecordsGrid } from "../components/review/RecordsGrid";
import { ResolutionPanel, type PanelExtensions } from "../components/review/ResolutionPanel";
import { ReviewHeader } from "../components/review/ReviewHeader";
import { RunBanner } from "../components/review/RunBanner";
import { makeSourceRequest, SourceViewer, type SourceRequest } from "../components/review/SourceViewer";
import { SummaryStrip } from "../components/review/SummaryStrip";
import { filterRows, findNameField, isNavigable, type RowFilter } from "../lib/reviewIssues";
import { useReviewData } from "../lib/useReviewData";
import { useReviewSession, type ReviewSession } from "../lib/useReviewSession";
import "./ReviewPage.css";

/** What the bottom bar gets: the loaded data, the session and the reload calls. */
export interface BottomBarContext {
  run: RunDetail;
  view: ReviewView;
  fields: RunField[];
  session: ReviewSession;
  reload: () => Promise<unknown>;
  refreshRun: () => Promise<void>;
}

/** What M13 can add: panel slots, the excluded row's Restore link and the bottom action bar. */
export interface ReviewExtensions extends PanelExtensions {
  renderExclusionAction?: (row: ReviewRow, session: ReviewSession) => ReactNode;
  renderBottomBar?: (context: BottomBarContext) => ReactNode;
}

/** Props of the screen: the run and, from M13, its extensions. */
interface ReviewPageProps {
  runId: string;
  extensions?: ReviewExtensions;
}

// Run statuses whose records can be reviewed
const REVIEWABLE_STATUSES = new Set(["in_review", "rechecking"]);

/** Show one run's review screen. */
export function ReviewPage({ runId, extensions }: ReviewPageProps) {
  const data = useReviewData(runId);
  const { run, view, fieldList } = data;
  // Wait for the first answer: an error with Try again, or a loading line
  if (run === null || view === null || fieldList === null) {
    return (
      <main className="page">
        {data.errorMessage !== null ? <LoadError message={data.errorMessage} onRetry={() => void data.reload()} /> : <p className="muted">Loading the review…</p>}
      </main>
    );
  }
  if (!REVIEWABLE_STATUSES.has(run.status)) {
    return <NotReviewable run={run} />;
  }
  return <ReviewScreen run={run} view={view} fieldList={fieldList} data={data} extensions={extensions} />;
}

/** Show a loading error with a button to load again. */
function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="review__load-error">
      <ErrorMessage message={message} />
      <button type="button" className="button-secondary" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

/** A run still processing or failed: point to its processing screen. */
function NotReviewable({ run }: { run: RunDetail }) {
  return (
    <main className="page">
      <div className="page-heading">
        <h1>{run.name}</h1>
        <p>
          {run.status === "failed" ? "This run failed, so it has no records to review." : "This run is still being processed."}{" "}
          <Link to={`/runs/${run.run_id}`}>Open the run's progress</Link>.
        </p>
      </div>
    </main>
  );
}

/** Props of the loaded screen. */
interface ReviewScreenProps {
  run: RunDetail;
  view: ReviewView;
  fieldList: NonNullable<ReturnType<typeof useReviewData>["fieldList"]>;
  data: ReturnType<typeof useReviewData>;
  extensions?: ReviewExtensions;
}

/** The loaded screen: everything above the grid, the grid with the panel, and the source viewer. */
function ReviewScreen({ run, view, fieldList, data, extensions }: ReviewScreenProps) {
  // A saved change removes a verified label in the API, so the run is read again to show it
  const session = useReviewSession(run.run_id, view, run.has_pending_changes, data.reload, run.is_verified ? data.refreshRun : undefined);
  const [filter, setFilter] = useState<RowFilter>("all");
  const [sourceRequest, setSourceRequest] = useState<SourceRequest | null>(null);
  const fields = fieldList.fields;
  const nameField = findNameField(fields);
  const { selection } = session;

  // Open the source viewer (the issue's cited locations first, then the value's evidence, else
  // the record's Found in); opening it for an issue counts as "source viewed"
  const openSource = (title: string, sources: CellSource[], locations: SourceLocation[], fallback: ReviewRow | null, issueId: string | null) => {
    const hasAny = sources.length > 0 || locations.length > 0;
    setSourceRequest(hasAny ? makeSourceRequest(title, sources, locations) : makeRowSourceRequest(fallback));
    if (issueId !== null) session.markSourceViewed(issueId);
  };

  // A clicked value opens the panel on its field, and on its first open issue if it has one
  const openCell = (row: ReviewRow, cell: ReviewCell) => {
    const issue = cell.issues.find(isNavigable) ?? cell.issues.find((item) => item.status === "open") ?? cell.issues[0];
    void session.select({ recordId: row.record_id, issueId: issue?.issue_id ?? null, field: cell.field });
  };
  // "Review" in the banner opens the panel on that run issue
  const openRunIssue = (issue: IssueSummary) => void session.select({ recordId: null, issueId: issue.issue_id, field: null });

  return (
    <main className="page review">
      <ReviewHeader run={run} lookupListsVersion={fieldList.lookup_lists_version} onRenamed={data.replaceRun} />
      <RunBanner runId={run.run_id} issues={view.run_issues} onReviewIssue={openRunIssue} />
      <SummaryStrip counts={view.counts} filter={filter} onFilter={setFilter} />
      <PendingNote session={session} />
      {data.errorMessage !== null && <ErrorMessage message={data.errorMessage} />}
      <div className={selection !== null ? "review__body review__body--with-panel" : "review__body"}>
        <RecordsGrid
          rows={filterRows(view.rows, filter)}
          totalCount={view.rows.length}
          fields={fields}
          nameField={nameField}
          selectedRecordId={selection?.recordId ?? null}
          selectedField={selection?.field ?? null}
          onOpenCell={openCell}
          onOpenFoundIn={(row) => setSourceRequest(makeRowSourceRequest(row))}
          renderExclusionAction={extensions?.renderExclusionAction !== undefined ? (row) => extensions.renderExclusionAction?.(row, session) : undefined}
        />
        {selection !== null && (
          <ResolutionPanel run={run} view={view} fields={fields} selection={selection} session={session} onOpenSource={openSource} extensions={extensions} />
        )}
      </div>
      {extensions?.renderBottomBar?.({ run, view, fields, session, reload: data.reload, refreshRun: data.refreshRun })}
      {sourceRequest !== null && <SourceViewer runId={run.run_id} request={sourceRequest} onClose={() => setSourceRequest(null)} />}
    </main>
  );
}

/** Build a source request for a record's "Found in" locations, highlighting its quotes. */
function makeRowSourceRequest(row: ReviewRow | null): SourceRequest {
  if (row === null) {
    return makeSourceRequest("Source", []);
  }
  const quotes = row.cells.flatMap((cell) => [...cell.sources, ...cell.alternatives.flatMap((alternative) => alternative.sources)]);
  // Only quotes from the found-in chunks; the locations keep the found-in order
  const foundIds = new Set(row.found_in.map((location) => location.chunk_id));
  const inFound = quotes.filter((source) => foundIds.has(source.location.chunk_id));
  return makeSourceRequest(`Found in: ${row.name ?? "record"}`, inFound, row.found_in);
}

/** Say that saved changes are re-checked when the user moves on, with "Re-check now"; and re-check errors. */
function PendingNote({ session }: { session: ReviewSession }) {
  return (
    <>
      {session.recheckError !== null && <ErrorMessage message={session.recheckError} />}
      {session.hasPendingChanges && (
        <div className="review__pending" role="status">
          <span>Your saved changes are checked when you move to another record.</span>
          <button type="button" className="button-text" disabled={session.isBusy} onClick={() => void session.recheckNow()}>
            {session.isBusy ? "Checking…" : "Re-check now"}
          </button>
        </div>
      )}
    </>
  );
}
