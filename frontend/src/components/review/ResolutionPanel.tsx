// The resolution panel (UI_SPEC §4.3): Previous / Next issue across the run, the record's
// issue list, the selected issue expanded with its action, and "Save and next issue".
// Extension slots let M13 add bulk actions and "Exclude record" without changing this file's flow.
// Issues naming existing types show the side-by-side duplicate comparison.
import { useCallback, useState, type ReactNode } from "react";
import type { CellAlternative, CellSource, ReviewCell, ReviewRow, ReviewView, RunDetail, RunField, SourceLocation } from "../../api/types";
import {
  buildChoice,
  describeAcceptLabel,
  findActionRule,
  makeEmptyActionState,
  type ActionState,
  type IssueChoice,
} from "../../lib/issueActions";
import {
  findCell,
  findNeighbourIssue,
  findRow,
  listOpenIssues,
  listRowIssues,
  listRunIssues,
  type IssueRef,
} from "../../lib/reviewIssues";
import { describeIssueDetails, useIssueDetails } from "../../lib/useIssueDetails";
import { selectionFor, type ReviewSession, type Selection } from "../../lib/useReviewSession";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";
import { SeverityIcon } from "./ActionNeeded";
import { DuplicateComparison } from "./DuplicateComparison";
import { IssueAction } from "./IssueActions";
import "./ResolutionPanel.css";

/** What "Save and next issue" runs instead of the plain save, when an extra sets one. */
export type SaveHandler = () => void;

/**
 * What the issue extras get: the run, the session, the issue, its record and the user's choice
 * (if ready), and `setSaveHandler` to take over "Save and next issue" (null gives it back).
 */
export interface IssueExtrasContext {
  run: RunDetail;
  session: ReviewSession;
  issue: IssueRef;
  row: ReviewRow | null;
  choice: IssueChoice | null;
  setSaveHandler: (handler: SaveHandler | null) => void;
}

/** What the footer's left side gets: the session and the record (null for run issues). */
export interface FooterContext {
  session: ReviewSession;
  row: ReviewRow | null;
}

/** What M13 can add to the panel: extra actions under an issue, and the footer's left side. */
export interface PanelExtensions {
  renderIssueExtras?: (context: IssueExtrasContext) => ReactNode;
  renderFooterStart?: (context: FooterContext) => ReactNode;
}

/** Props of the panel. */
interface ResolutionPanelProps {
  run: RunDetail;
  view: ReviewView;
  fields: RunField[];
  selection: Selection;
  session: ReviewSession;
  // Evidence pairs (quotes highlighted), the issue's cited locations, and the row to fall back on
  onOpenSource: (title: string, sources: CellSource[], locations: SourceLocation[], fallback: ReviewRow | null, issueId: string | null) => void;
  extensions?: PanelExtensions;
}

/** Show the panel for the selected record (or the run's issues). */
export function ResolutionPanel(props: ResolutionPanelProps) {
  const { run, view, fields, selection, session } = props;
  const row = selection.recordId !== null ? findRow(view, selection.recordId) : null;
  const refs = row !== null ? listRowIssues(row) : listRunIssues(view);
  const details = useIssueDetails(run, selection.recordId, view);
  const columnOf = (field: string | null) => (field === null ? (row !== null ? "Record" : "Run") : fields.find((item) => item.key === field)?.column ?? field);
  return (
    <aside className="panel" aria-label="Resolution panel">
      <PanelTop {...props} />
      <h2 className="panel__record">{row !== null ? row.name ?? "Unnamed record" : "Run issues"}</h2>
      <IssueList refs={refs} selection={selection} session={session} columnOf={columnOf} />
      {details.errorMessage !== null && <ErrorMessage message={details.errorMessage} />}
      {/* A new key gives each issue (or field) a fresh, empty action state */}
      <ExpandedIssue key={`${selection.recordId}|${selection.issueId}|${selection.field}`} {...props} row={row} refs={refs} columnOf={columnOf} detailIssues={details.issues} />
    </aside>
  );
}

/** Previous / Next issue arrows with "Issue i of n open", and the close button. */
function PanelTop({ view, selection, session }: ResolutionPanelProps) {
  const open = listOpenIssues(view, session.savedIssueIds);
  const position = open.findIndex((ref) => ref.issue.issue_id === selection.issueId);
  const label = position >= 0 ? `Issue ${position + 1} of ${open.length} open` : `${open.length} open ${open.length === 1 ? "issue" : "issues"}`;
  // Move to the neighbouring open issue (re-checks first when it is on another record)
  const go = (step: 1 | -1) => {
    const next = findNeighbourIssue(view, session.savedIssueIds, selection.issueId, step);
    if (next !== null) void session.select(selectionFor(next));
  };
  return (
    <div className="panel__top">
      <button type="button" className="panel__arrow" aria-label="Previous issue" disabled={open.length === 0 || session.isBusy} onClick={() => go(-1)}>
        <Icon name="chevron-left" />
      </button>
      <span className="panel__position" aria-live="polite">{label}</span>
      <button type="button" className="panel__arrow" aria-label="Next issue" disabled={open.length === 0 || session.isBusy} onClick={() => go(1)}>
        <Icon name="chevron-right" />
      </button>
      <button type="button" className="icon-button panel__close" aria-label="Close panel" onClick={() => void session.select(null)}>
        <Icon name="close" />
      </button>
    </div>
  );
}

/** The record's issues: icon, field and short label; clicking one selects it. */
function IssueList({ refs, selection, session, columnOf }: { refs: IssueRef[]; selection: Selection; session: ReviewSession; columnOf: (field: string | null) => string }) {
  if (refs.length === 0) {
    return <p className="muted panel__empty">No open issues.</p>;
  }
  return (
    <ul className="panel__issues" aria-label="Issues of this record">
      {refs.map((ref) => {
        const isSelected = ref.issue.issue_id === selection.issueId;
        const rule = findActionRule(ref.issue, ref.field !== null);
        const state = describeIssueState(ref, session.savedIssueIds);
        return (
          <li key={ref.issue.issue_id}>
            <button type="button" className={`panel__issue${isSelected ? " panel__issue--selected" : ""}`} aria-current={isSelected} onClick={() => void session.selectIssue(ref)}>
              <SeverityIcon severity={ref.issue.severity} />
              <strong>{columnOf(ref.field)}</strong>
              <span className="muted">{rule.shortLabel}</span>
              {state !== null && <span className="panel__issue-state">{state}</span>}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** Return "Accepted" or "Saved" for an issue that waits for nothing, or null while open. */
function describeIssueState(ref: IssueRef, savedIds: ReadonlySet<string>): string | null {
  if (ref.issue.status === "accepted") return "Accepted";
  return savedIds.has(ref.issue.issue_id) ? "Saved · checked when you move on" : null;
}

/** Props of the expanded part: the panel's props plus the row, its issues and helpers. */
interface ExpandedIssueProps extends ResolutionPanelProps {
  row: ReviewRow | null;
  refs: IssueRef[];
  columnOf: (field: string | null) => string;
  detailIssues: ResolutionPanelProps["run"]["run_issues"];
}

/** The selected issue (or field) with its message, details, action and the Save button. */
function ExpandedIssue(props: ExpandedIssueProps) {
  const { view, fields, selection, session, row, refs, columnOf, detailIssues, onOpenSource, extensions } = props;
  const [state, setState] = useState<ActionState>(makeEmptyActionState);
  // An extra (e.g. "Also apply to N similar") may take over Save and next
  const [saveHandler, setSaveHandler] = useState<SaveHandler | null>(null);
  const changeSaveHandler = useCallback((handler: SaveHandler | null) => setSaveHandler(() => handler), []);
  const ref = refs.find((item) => item.issue.issue_id === selection.issueId) ?? null;
  const fieldKey = ref?.field ?? selection.field;
  const cell = row !== null && fieldKey !== null ? findCell(row, fieldKey) : null;
  const field = fields.find((item) => item.key === fieldKey) ?? null;
  const rule = ref !== null ? findActionRule(ref.issue, ref.field !== null) : null;
  const issueId = ref?.issue.issue_id ?? null;
  const isSourceViewed = issueId !== null && session.viewedSourceIssueIds.has(issueId);
  // The value's evidence, plus the passages the issue itself cites (run issues have only these)
  const sources = collectSources(cell);
  const issueLocations = ref?.issue.sources ?? [];
  const hasSources = sources.length > 0 || issueLocations.length > 0 || (row !== null && row.found_in.length > 0);
  // Nothing is selected yet: ask the user to pick an issue or a value
  if (ref === null && (fieldKey === null || cell === null)) {
    return <p className="muted panel__empty">Choose an issue above, or click a value in the grid.</p>;
  }
  const result = buildChoice({ issue: ref?.issue ?? null, kind: rule?.kind ?? null, recordId: selection.recordId, field, isSourceViewed }, state);
  const nameOf = (recordId: string) => findRow(view, recordId)?.name ?? recordId;
  const detailIssue = detailIssues.find((issue) => issue.issue_id === issueId);
  const detailLines = describeIssueDetails(detailIssue, nameOf);
  const candidates = ref?.issue.duplicate_candidates ?? [];
  const title = columnOf(fieldKey);
  // Save the choice, through the extra's handler when one is set
  const save = (choice: IssueChoice | null) => {
    if (choice === null) return;
    if (saveHandler !== null) saveHandler();
    else void session.saveAndNext(choice);
  };
  return (
    <section className="panel__expanded" aria-label="Selected issue">
      <h3 className="panel__issue-title">{ref !== null ? `${title} · ${rule?.shortLabel}` : `${title} · Change value`}</h3>
      {ref !== null && <p className="panel__message">{ref.issue.message}</p>}
      {detailLines.map((line) => (
        <p key={line} className="panel__detail">{line}</p>
      ))}
      {/* Possible duplicates: this record next to the existing types the issue names */}
      <DuplicateComparison row={row} fields={fields} candidates={candidates} referenceVersion={props.run.reference_data_version} />
      <IssueAction
        kind={rule?.kind ?? null}
        acceptLabel={rule !== null ? describeAcceptLabel(rule) : ""}
        issue={ref?.issue ?? null}
        cell={cell}
        field={field}
        state={state}
        isSourceViewed={isSourceViewed}
        hasSources={hasSources}
        isRunIssue={selection.recordId === null}
        onState={(patch) => setState((current) => ({ ...current, ...patch }))}
        onViewSource={() => onOpenSource(title, sources, issueLocations, row, issueId)}
        onShowAlternativeSource={(alternative: CellAlternative) => onOpenSource(`${title}: ${alternative.value}`, alternative.sources, [], null, issueId)}
        extraActions={ref !== null ? extensions?.renderIssueExtras?.({ run: props.run, session, issue: ref, row, choice: result.choice, setSaveHandler: changeSaveHandler }) : null}
      />
      <footer className="panel__footer">
        <div>{extensions?.renderFooterStart?.({ session, row })}</div>
        <div className="panel__save">
          <button type="button" className="panel__save-button" disabled={result.choice === null || session.isBusy} onClick={() => save(result.choice)}>
            {session.isBusy ? "Working…" : "Save and next issue"}
          </button>
          {result.hint !== null && <span className="panel__hint">{result.hint}</span>}
        </div>
      </footer>
      {session.saveError !== null && <ErrorMessage message={session.saveError} />}
    </section>
  );
}

/** Return every evidence pair of a cell: its own sources, then each alternative's. */
function collectSources(cell: ReviewCell | null): CellSource[] {
  if (cell === null) return [];
  return [...cell.sources, ...cell.alternatives.flatMap((alternative) => alternative.sources)];
}
