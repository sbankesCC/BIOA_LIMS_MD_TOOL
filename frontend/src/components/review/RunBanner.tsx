// The run-level banner (UI_SPEC §4.3): the run's open issues (scanned pages, unreadable files,
// items that may be missing). The X dismisses it for this run; a later new run issue shows it again.
import { useState } from "react";
import type { IssueSummary } from "../../api/types";
import { readDismissedIssueIds, writeDismissedIssueIds } from "../../lib/bannerDismissal";
import { isNavigable } from "../../lib/reviewIssues";
import { Icon } from "../Icon";
import { SeverityIcon } from "./ActionNeeded";
import "./RunBanner.css";

/** Props of the banner: the run, its issues, and what "Review" on an issue does. */
interface RunBannerProps {
  runId: string;
  issues: IssueSummary[];
  onReviewIssue: (issue: IssueSummary) => void;
}

/** Show the run's open issues until the user dismisses them for this run. */
export function RunBanner({ runId, issues, onReviewIssue }: RunBannerProps) {
  const [dismissedIds, setDismissedIds] = useState(() => readDismissedIssueIds(runId));
  const openIssues = issues.filter((issue) => issue.status === "open");
  const hasNewIssue = openIssues.some((issue) => !dismissedIds.includes(issue.issue_id));
  if (openIssues.length === 0 || !hasNewIssue) {
    return null;
  }

  // Remember every issue shown now as dismissed for this run
  const dismiss = () => {
    const ids = openIssues.map((issue) => issue.issue_id);
    writeDismissedIssueIds(runId, ids);
    setDismissedIds(ids);
  };

  return (
    <section className="run-banner" aria-label="Run messages">
      <ul className="run-banner__list">
        {openIssues.map((issue) => (
          <li key={issue.issue_id} className="run-banner__item">
            <SeverityIcon severity={issue.severity} />
            <span>{issue.message}</span>
            {isNavigable(issue) && (
              <button type="button" className="button-text" onClick={() => onReviewIssue(issue)}>
                Review
              </button>
            )}
          </li>
        ))}
      </ul>
      <button type="button" className="icon-button" aria-label="Dismiss run messages" onClick={dismiss}>
        <Icon name="close" />
      </button>
    </section>
  );
}
