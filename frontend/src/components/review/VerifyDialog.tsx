// The Verify dialog (UI_SPEC §4.4, mockup 3b): red issues and individual-review warnings block
// Verify and are listed with links to each; other warnings are accepted by the verifier with
// "Accept warnings and verify". With nothing open, Verify runs at once (POST /runs/{id}/verify).
import { useEffect, useRef, useState } from "react";
import { useApiClient } from "../../api/client";
import { describeError } from "../../api/errors";
import { verifyRun } from "../../api/review";
import type { ReviewView, RunDetail, VerifyResult } from "../../api/types";
import { findActionRule } from "../../lib/issueActions";
import { findCell, findRow, type IssueRef } from "../../lib/reviewIssues";
import { selectionFor, type ReviewSession } from "../../lib/useReviewSession";
import { checkVerifyResult, checkView, isBlocked, isClear, type VerifyCheck } from "../../lib/verifyCheck";
import { Dialog } from "../Dialog";
import { ErrorMessage } from "../ErrorMessage";
import { SeverityIcon } from "./ActionNeeded";
import { PRODUCTION_REMINDER } from "./reviewText";
import "./VerifyDialog.css";

/** Props of the dialog: the run, the view, the session, reload and what closing does. */
interface VerifyDialogProps {
  run: RunDetail;
  view: ReviewView;
  session: ReviewSession;
  reload: () => Promise<unknown>;
  onClose: () => void;
}

/** Show the open items that stop or come with Verify, and verify when allowed. */
export function VerifyDialog({ run, view, session, reload, onClose }: VerifyDialogProps) {
  const client = useApiClient();
  const [refusal, setRefusal] = useState<VerifyResult | null>(null);
  const [isVerifying, setIsVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasStarted = useRef(false);
  // A refused answer lists the API's blockers; otherwise the view's open issues count
  const check = refusal !== null ? checkVerifyResult(refusal) : checkView(view);

  // Verify, then reload: a verified run closes the dialog, a refused one shows its blockers
  const verify = async () => {
    hasStarted.current = true;
    setIsVerifying(true);
    setErrorMessage(null);
    try {
      const result = await verifyRun(client, run.run_id);
      await reload();
      if (result.is_verified) onClose();
      else setRefusal(result);
    } catch (error) {
      setErrorMessage(describeError(error));
    } finally {
      setIsVerifying(false);
    }
  };

  // Nothing open when the dialog opens: verify at once (only once)
  useEffect(() => {
    if (!hasStarted.current && isClear(checkView(view))) void verify();
    // Runs on open only; later views come from this dialog's own reload
  }, []);

  // Close the dialog and open the panel on an issue
  const goTo = (ref: IssueRef) => {
    onClose();
    void session.select(selectionFor(ref));
  };
  const isOpenItems = !isClear(check);
  return (
    <Dialog
      title={isOpenItems ? "Your review isn't finished" : "Verify output"}
      onClose={onClose}
      actions={
        <>
          {isOpenItems && (
            <button type="button" className="button-secondary" disabled={isBlocked(check) || isVerifying} onClick={() => void verify()}>
              {isVerifying ? "Verifying…" : "Accept warnings and verify"}
            </button>
          )}
          <button type="button" className="dialog__primary" onClick={onClose}>
            Keep reviewing
          </button>
        </>
      }
    >
      <p>Verifying confirms you reviewed this run; exports are then no longer drafts. Any later change removes the verified label.</p>
      {isOpenItems ? <OpenItems check={check} view={view} onGoTo={goTo} /> : <p className="muted">{isVerifying ? "Checking and verifying the run…" : "Nothing is open."}</p>}
      {refusal !== null && <p className="dialog__hint">The run changed since this screen loaded, so it was not verified.</p>}
      <p className="dialog__reminder">Reminder: {PRODUCTION_REMINDER}</p>
      {errorMessage !== null && <ErrorMessage message={errorMessage} />}
    </Dialog>
  );
}

/** The three groups of open items, each with its sentence and, for blockers, links. */
function OpenItems({ check, view, onGoTo }: { check: VerifyCheck; view: ReviewView; onGoTo: (ref: IssueRef) => void }) {
  const { errors, individualWarnings, otherWarnings } = check;
  return (
    <div className="verify__groups">
      {errors.length > 0 && (
        <div className="verify__group verify__group--red">
          <p>
            <strong>{countIssues(errors.length, "issue")} to fix.</strong> These must be resolved before you can verify.
          </p>
          <IssueLinks refs={errors} view={view} onGoTo={onGoTo} />
        </div>
      )}
      {individualWarnings.length > 0 && (
        <div className="verify__group verify__group--amber">
          <p>
            <strong>{countIssues(individualWarnings.length, "warning")} must be reviewed one at a time.</strong>{" "}
            <button type="button" className="button-text" onClick={() => onGoTo(individualWarnings[0])}>
              Review the first one
            </button>
          </p>
          <IssueLinks refs={individualWarnings} view={view} onGoTo={onGoTo} />
        </div>
      )}
      {otherWarnings.length > 0 && (
        <div className="verify__group verify__group--amber">
          <p>
            <strong>{countIssues(otherWarnings.length, "warning")} not reviewed.</strong> If you verify, they are accepted as they are.
          </p>
        </div>
      )}
    </div>
  );
}

/** Return "1 issue" or "N issues" (or warnings). */
function countIssues(count: number, word: string): string {
  return `${count} ${count === 1 ? word : `${word}s`}`;
}

/** A list of issues as buttons: record · column · short label; clicking opens the issue. */
function IssueLinks({ refs, view, onGoTo }: { refs: IssueRef[]; view: ReviewView; onGoTo: (ref: IssueRef) => void }) {
  return (
    <ul className="verify__links">
      {refs.map((ref) => (
        <li key={ref.issue.issue_id}>
          <button type="button" className="verify__link" onClick={() => onGoTo(ref)}>
            <SeverityIcon severity={ref.issue.severity} />
            <span>{describeIssuePlace(ref, view)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** Return where an issue sits and what it is: "Record name · Column · short label". */
function describeIssuePlace(ref: IssueRef, view: ReviewView): string {
  const row = ref.recordId !== null ? findRow(view, ref.recordId) : null;
  const place = ref.recordId === null ? "Run" : row?.name ?? ref.recordId;
  const column = row !== null && ref.field !== null ? findCell(row, ref.field)?.column ?? ref.field : "Record";
  const label = findActionRule(ref.issue, ref.field !== null).shortLabel;
  return ref.recordId === null ? `${place} · ${label}` : `${place} · ${column} · ${label}`;
}
