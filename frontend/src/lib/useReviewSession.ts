// The Review screen's working state: which record, field and issue the panel shows, changes
// saved but not yet re-checked, sources the user opened, and the save and re-check calls.
// Re-check runs when the user moves to another record (UI_SPEC §4.3 "Saving and re-checking").
import { useCallback, useRef, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { recheckRun, saveChanges } from "../api/review";
import type { Change, ReviewView } from "../api/types";
import { makeChangeId } from "./ids";
import type { IssueChoice, NewChange } from "./issueActions";
import { findFirstOpenIssue, findIssueRef, findNeighbourIssue, findRow, type IssueRef } from "./reviewIssues";

/** What the panel shows: a record (null for run issues), an issue and a field (either may be null). */
export interface Selection {
  recordId: string | null;
  issueId: string | null;
  field: string | null;
}

/** The session state and actions the screen and the panel use (and M13 builds on). */
export interface ReviewSession {
  selection: Selection | null;
  savedIssueIds: ReadonlySet<string>;
  viewedSourceIssueIds: ReadonlySet<string>;
  hasPendingChanges: boolean;
  isBusy: boolean;
  saveError: string | null;
  recheckError: string | null;
  select: (next: Selection | null) => Promise<void>;
  selectIssue: (ref: IssueRef) => Promise<void>;
  markSourceViewed: (issueId: string) => void;
  submitChanges: (changes: NewChange[] | Change[]) => Promise<boolean>;
  saveAndNext: (choice: IssueChoice) => Promise<void>;
  recheckNow: () => Promise<void>;
}

/** Return the selection for an issue reference. */
export function selectionFor(ref: IssueRef): Selection {
  return { recordId: ref.recordId, issueId: ref.issue.issue_id, field: ref.field };
}

/** Keep a selection valid after a reload: same issue if it still exists, else the record's first issue. */
function reconcileSelection(view: ReviewView, target: Selection): Selection | null {
  if (target.issueId !== null && findIssueRef(view, target.issueId) !== null) {
    return target;
  }
  // The record may have gone; a run selection always stays
  if (target.recordId !== null && findRow(view, target.recordId) === null) {
    return null;
  }
  const first = findFirstOpenIssue(view, target.recordId);
  return first !== null ? selectionFor(first) : { ...target, issueId: null };
}

/**
 * Hold the review session for one run; `reload` reads the view again and returns it.
 * `onChangesSaved` runs after changes are stored (the API then removes a verified label).
 */
export function useReviewSession(
  runId: string,
  view: ReviewView | null,
  hasStoredPendingChanges: boolean,
  reload: () => Promise<ReviewView | null>,
  onChangesSaved?: () => void,
): ReviewSession {
  const client = useApiClient();
  const [selection, setSelection] = useState<Selection | null>(null);
  const [savedIssueIds, setSavedIssueIds] = useState<ReadonlySet<string>>(new Set());
  const [viewedSourceIssueIds, setViewedSourceIssueIds] = useState<ReadonlySet<string>>(new Set());
  // Null until this screen saves or re-checks; until then the run's stored flag counts
  const [pendingOverride, setPendingOverride] = useState<boolean | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [recheckError, setRecheckError] = useState<string | null>(null);
  const hasPendingChanges = pendingOverride ?? hasStoredPendingChanges;
  // The latest selection, read by async steps that started before a render
  const selectionRef = useRef<Selection | null>(null);
  selectionRef.current = selection;

  // Re-check the run, reload the view and keep the panel on a valid issue of the target record
  const recheckAndShow = useCallback(
    async (target: Selection | null) => {
      setIsBusy(true);
      setRecheckError(null);
      try {
        await recheckRun(client, runId);
        setPendingOverride(false);
        setSavedIssueIds(new Set());
        const newView = await reload();
        if (newView !== null && target !== null) {
          setSelection(reconcileSelection(newView, target));
        }
      } catch (error) {
        setRecheckError(describeError(error));
      } finally {
        setIsBusy(false);
      }
    },
    [client, runId, reload],
  );

  // Move the panel; moving to another record with saved changes re-checks first
  const moveTo = useCallback(
    async (next: Selection | null, isPendingNow: boolean) => {
      const current = selectionRef.current;
      const isOtherRecord = current !== null && next !== null && next.recordId !== current.recordId;
      setSelection(next);
      setSaveError(null);
      if (isOtherRecord && isPendingNow) {
        await recheckAndShow(next);
      }
    },
    [recheckAndShow],
  );

  const select = useCallback((next: Selection | null) => moveTo(next, hasPendingChanges), [moveTo, hasPendingChanges]);
  const selectIssue = useCallback((ref: IssueRef) => select(selectionFor(ref)), [select]);

  // Store changes as pending, each with a new change ID
  const submitChanges = useCallback(
    async (changes: NewChange[] | Change[]): Promise<boolean> => {
      setIsBusy(true);
      setSaveError(null);
      try {
        const withIds = changes.map((change) => ({ ...change, change_id: makeChangeId() }) as Change);
        await saveChanges(client, runId, withIds);
        setPendingOverride(true);
        onChangesSaved?.();
        return true;
      } catch (error) {
        setSaveError(describeError(error));
        return false;
      } finally {
        setIsBusy(false);
      }
    },
    [client, runId, onChangesSaved],
  );

  // Save the choice (if it changes anything), then go to the next open issue
  const saveAndNext = useCallback(
    async (choice: IssueChoice) => {
      const current = selectionRef.current;
      if (view === null || current === null) return;
      let saved = savedIssueIds;
      let isPendingNow = hasPendingChanges;
      if (choice.kind === "change") {
        if (!(await submitChanges([choice.change]))) return;
        isPendingNow = true;
        // The saved issue waits for the re-check, so the arrows skip it
        if (current.issueId !== null) {
          saved = new Set([...savedIssueIds, current.issueId]);
          setSavedIssueIds(saved);
        }
      }
      const next = findNeighbourIssue(view, saved, current.issueId, 1);
      if (next !== null) {
        await moveTo(selectionFor(next), isPendingNow);
      } else if (isPendingNow) {
        // No issue is left to move to: re-check now so the results show
        await recheckAndShow({ ...current, issueId: null });
      }
    },
    [view, savedIssueIds, hasPendingChanges, submitChanges, moveTo, recheckAndShow],
  );

  const recheckNow = useCallback(() => recheckAndShow(selectionRef.current), [recheckAndShow]);

  // Remember that the user opened an issue's source (needed to accept individual-review warnings)
  const markSourceViewed = useCallback((issueId: string) => {
    setViewedSourceIssueIds((ids) => new Set([...ids, issueId]));
  }, []);

  return {
    selection,
    savedIssueIds,
    viewedSourceIssueIds,
    hasPendingChanges,
    isBusy,
    saveError,
    recheckError,
    select,
    selectIssue,
    markSourceViewed,
    submitChanges,
    saveAndNext,
    recheckNow,
  };
}
