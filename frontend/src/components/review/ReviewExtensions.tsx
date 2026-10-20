// The M13 additions to the Review screen, plugged in through ReviewPage's `extensions`: bulk
// actions under the selected issue, Exclude / Restore, and the bottom bar with Undo, Verify
// and Export. Undo reads the API's bulk action list, so no bulk state is kept here.
import { ReviewPage, type ReviewExtensions } from "../../pages/ReviewPage";
import { ActionBar } from "./ActionBar";
import { BulkActions } from "./BulkActions";
import { RecordExclusionAction, RestoreButton } from "./RecordExclusion";

// The extensions of every run's Review screen
const REVIEW_EXTENSIONS: ReviewExtensions = {
  renderIssueExtras: (context) => <BulkActions {...context} />,
  renderFooterStart: ({ row, session }) => <RecordExclusionAction row={row} session={session} />,
  renderExclusionAction: (row, session) => <RestoreButton row={row} session={session} />,
  renderBottomBar: (context) => <ActionBar {...context} />,
};

/** The Review screen of one run with every M13 action. */
export function ReviewWithActions({ runId }: { runId: string }) {
  return <ReviewPage runId={runId} extensions={REVIEW_EXTENSIONS} />;
}
