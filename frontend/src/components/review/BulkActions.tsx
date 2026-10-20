// Bulk actions under the selected issue (UI_SPEC §4.3 "Bulk actions"): Change all, Fill missing,
// Accept all of a type and Resolve repeated conflicts. Each offer loads its bulk preview, says
// how many records it touches, and opens the confirmation list before anything is sent.
import { useState } from "react";
import type { RunDetail } from "../../api/types";
import { describeOffer, describeOfferButton, findBulkOffers, isSelectedMatch, type BulkOffer, type BulkOfferContext } from "../../lib/bulkActions";
import { findActionRule } from "../../lib/issueActions";
import { useBulkPreview } from "../../lib/useBulkPreview";
import type { ReviewSession } from "../../lib/useReviewSession";
import { ErrorMessage } from "../ErrorMessage";
import { BulkConfirmDialog, type SavedBulk } from "./BulkConfirmDialog";
import "./BulkActions.css";

/** Props of the bulk actions: the run, the session, the selected issue and what a saved bulk does. */
interface BulkActionsProps extends BulkOfferContext {
  run: RunDetail;
  session: ReviewSession;
  onBulkSaved: (bulk: SavedBulk) => void;
}

/** Show every bulk action the selected issue offers (none for individual-review warnings). */
export function BulkActions(props: BulkActionsProps) {
  const offers = findBulkOffers(props);
  if (offers.length === 0) return null;
  const shortLabel = findActionRule(props.issue.issue, props.issue.field !== null).shortLabel;
  return (
    <div className="bulk-actions">
      {offers.map((offer) => (
        <BulkOfferBox key={offer.mode} {...props} offer={offer} shortLabel={shortLabel} />
      ))}
    </div>
  );
}

/** Props of one offer: the bulk actions' props plus the offer and the issue's short label. */
interface BulkOfferBoxProps extends BulkActionsProps {
  offer: BulkOffer;
  shortLabel: string;
}

/** One offer: its preview count, its sentence and the button that opens the confirmation list. */
function BulkOfferBox({ run, session, offer, shortLabel, onBulkSaved }: BulkOfferBoxProps) {
  const { preview, errorMessage } = useBulkPreview(run.run_id, offer.request);
  const [isConfirming, setIsConfirming] = useState(false);
  if (errorMessage !== null) {
    return <ErrorMessage message={errorMessage} />;
  }
  // Offer only when the action reaches at least one other record
  if (preview === null) return null;
  const others = preview.matches.filter((match) => !isSelectedMatch(offer, match)).length;
  if (others === 0) return null;
  const isValueMissing = offer.mode !== "accept_type" && offer.value === null;
  return (
    <div className="bulk-actions__offer">
      <p className="bulk-actions__text">{describeOffer(offer, preview.count, others, shortLabel)}</p>
      <div className="bulk-actions__row">
        <button type="button" className="button-secondary" disabled={isValueMissing || session.isBusy} onClick={() => setIsConfirming(true)}>
          {describeOfferButton(offer, preview.count)}
        </button>
        {isValueMissing && offer.mode === "change_all" && <span className="muted">Choose the new value above first.</span>}
      </div>
      {isConfirming && (
        <BulkConfirmDialog
          preview={preview}
          offer={offer}
          shortLabel={shortLabel}
          session={session}
          onClose={() => setIsConfirming(false)}
          onSaved={(bulk) => {
            setIsConfirming(false);
            onBulkSaved(bulk);
          }}
        />
      )}
    </div>
  );
}
