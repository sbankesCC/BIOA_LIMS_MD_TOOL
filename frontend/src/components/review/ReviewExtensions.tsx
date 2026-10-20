// The M13 additions to the Review screen, plugged in through ReviewPage's `extensions`: bulk
// actions under the selected issue, Exclude / Restore, and the bottom bar with Undo, Verify
// and Export. The last bulk action (for Undo) is kept here, shared by the panel and the bar.
import { useState } from "react";
import { ReviewPage, type ReviewExtensions } from "../../pages/ReviewPage";
import { ActionBar } from "./ActionBar";
import { BulkActions } from "./BulkActions";
import type { SavedBulk } from "./BulkConfirmDialog";
import { RecordExclusionAction, RestoreButton } from "./RecordExclusion";

/** Build the extensions of one run's Review screen. */
export function useReviewExtensions(): ReviewExtensions {
  const [lastBulk, setLastBulk] = useState<SavedBulk | null>(null);
  return {
    renderIssueExtras: (context) => <BulkActions {...context} onBulkSaved={setLastBulk} />,
    renderFooterStart: ({ row, session }) => <RecordExclusionAction row={row} session={session} />,
    renderExclusionAction: (row, session) => <RestoreButton row={row} session={session} />,
    renderBottomBar: (context) => <ActionBar {...context} lastBulk={lastBulk} onBulkUndone={() => setLastBulk(null)} />,
  };
}

/** The Review screen of one run with every M13 action. */
export function ReviewWithActions({ runId }: { runId: string }) {
  const extensions = useReviewExtensions();
  return <ReviewPage runId={runId} extensions={extensions} />;
}
