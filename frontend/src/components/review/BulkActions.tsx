// Bulk actions under the selected issue (UI_SPEC §4.3 "Bulk actions", mockup 3): the "Also apply
// to N similar" checkbox for the chosen value (Change all, Fill missing, Resolve repeated
// conflicts), and "Accept all of a type" for warnings. Each loads its bulk preview, counts the
// other records, and opens the confirmation list before anything is sent.
import { useEffect, useState } from "react";
import type { BulkPreview, RunDetail } from "../../api/types";
import { describeAcceptOffer, describeAlsoApply, findBulkOffers, isSelectedMatch, isValueOffer, type BulkOffer, type BulkOfferContext } from "../../lib/bulkActions";
import { findActionRule, type IssueChoice } from "../../lib/issueActions";
import { useBulkPreview } from "../../lib/useBulkPreview";
import type { ReviewSession } from "../../lib/useReviewSession";
import { ErrorMessage } from "../ErrorMessage";
import type { SaveHandler } from "./ResolutionPanel";
import { BulkConfirmDialog } from "./BulkConfirmDialog";
import "./BulkActions.css";

/** Props of the bulk actions: the run, the session, the selected issue and how to take over Save. */
interface BulkActionsProps extends BulkOfferContext {
  run: RunDetail;
  session: ReviewSession;
  setSaveHandler: (handler: SaveHandler | null) => void;
}

/** Show every bulk action the selected issue offers (none for individual-review warnings). */
export function BulkActions(props: BulkActionsProps) {
  const offers = findBulkOffers(props);
  if (offers.length === 0) return null;
  const shortLabel = findActionRule(props.issue.issue, props.issue.field !== null).shortLabel;
  return (
    <div className="bulk-actions">
      {offers.map((offer) =>
        isValueOffer(offer) ? (
          <AlsoApplyBox key={offer.mode} {...props} offer={offer} shortLabel={shortLabel} />
        ) : (
          <AcceptAllBox key={offer.mode} {...props} offer={offer} shortLabel={shortLabel} />
        ),
      )}
    </div>
  );
}

/** Props of one offer: the bulk actions' props plus the offer and the issue's short label. */
interface OfferBoxProps extends BulkActionsProps {
  offer: BulkOffer;
  shortLabel: string;
}

/** Return the number of preview matches that are other records (not the selected issue's own). */
function countOthers(offer: BulkOffer, preview: BulkPreview | null): number {
  if (preview === null) return 0;
  return preview.matches.filter((match) => !isSelectedMatch(offer, match)).length;
}

/**
 * The "Also apply to N similar" checkbox (unticked at first). Ticked, it takes over Save and next:
 * the confirmation list opens, and confirming saves this record's change and the checked others
 * as one bulk change. Hidden until the value is chosen and while no other record matches.
 */
function AlsoApplyBox({ run, session, offer, shortLabel, choice, setSaveHandler }: OfferBoxProps) {
  const { preview, errorMessage } = useBulkPreview(run.run_id, offer.request);
  const [isTicked, setIsTicked] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const others = countOthers(offer, preview);
  const current = readChange(choice);
  const isOffered = preview !== null && others > 0 && offer.value !== null && current !== null;
  const isActive = isOffered && isTicked;
  // Take over Save and next while the box is ticked; give it back when unticked or gone
  useEffect(() => {
    if (!isActive) return;
    setSaveHandler(() => setIsConfirming(true));
    return () => setSaveHandler(null);
  }, [isActive, setSaveHandler]);

  if (errorMessage !== null) return <ErrorMessage message={errorMessage} />;
  if (!isOffered) return null;
  return (
    <div>
      <label className="bulk-actions__also">
        <input type="checkbox" checked={isTicked} disabled={session.isBusy} onChange={(event) => setIsTicked(event.target.checked)} />
        <span>{describeAlsoApply(offer, others)}</span>
      </label>
      {isConfirming && (
        <BulkConfirmDialog
          preview={preview}
          offer={offer}
          shortLabel={shortLabel}
          session={session}
          currentChange={current}
          onClose={() => setIsConfirming(false)}
          onSaved={() => setIsConfirming(false)}
        />
      )}
    </div>
  );
}

/** Return the change of the user's choice, or null when there is nothing to save yet. */
function readChange(choice: IssueChoice | null) {
  return choice !== null && choice.kind === "change" ? choice.change : null;
}

/** "Accept all of a type": its preview count, its sentence and the button that opens the confirmation list. */
function AcceptAllBox({ run, session, offer, shortLabel }: OfferBoxProps) {
  const { preview, errorMessage } = useBulkPreview(run.run_id, offer.request);
  const [isConfirming, setIsConfirming] = useState(false);
  if (errorMessage !== null) return <ErrorMessage message={errorMessage} />;
  // Offer only when the action reaches at least one other record
  if (preview === null || countOthers(offer, preview) === 0) return null;
  return (
    <div className="bulk-actions__offer">
      <p className="bulk-actions__text">{describeAcceptOffer(preview.count, shortLabel)}</p>
      <div className="bulk-actions__row">
        <button type="button" className="button-secondary" disabled={session.isBusy} onClick={() => setIsConfirming(true)}>
          {`Accept all ${preview.count}…`}
        </button>
      </div>
      {isConfirming && (
        <BulkConfirmDialog
          preview={preview}
          offer={offer}
          shortLabel={shortLabel}
          session={session}
          currentChange={null}
          onClose={() => setIsConfirming(false)}
          onSaved={() => setIsConfirming(false)}
        />
      )}
    </div>
  );
}
