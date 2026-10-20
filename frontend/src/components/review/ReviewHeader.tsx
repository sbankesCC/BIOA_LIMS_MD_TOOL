// The Review screen header (UI_SPEC §4.3): run state, run name with rename (RunTitle, PATCH
// /runs/{id}), document count, lookup list version and reference data version.
import type { RunDetail } from "../../api/types";
import { RunTitle } from "../RunTitle";
import "./ReviewHeader.css";

/** Props of the header: the run, the run's lookup list version, and what a rename gives back. */
interface ReviewHeaderProps {
  run: RunDetail;
  lookupListsVersion: string;
  onRenamed: (run: RunDetail) => void;
}

/** Show the run's state, name (with rename) and versions. */
export function ReviewHeader({ run, lookupListsVersion, onRenamed }: ReviewHeaderProps) {
  const documentCount = run.documents.length;
  const meta = [
    `${documentCount} ${documentCount === 1 ? "document" : "documents"}`,
    `Lookup lists ${lookupListsVersion}`,
    `Reference data ${run.reference_data_version ?? "none"}`,
  ];
  const state = run.is_verified ? `Verified by ${run.verified_by ?? "a reviewer"}` : "In review";
  return (
    <div className="review-header page-heading">
      <div className="eyebrow">Run · {state}</div>
      <RunTitle run={run} onRenamed={onRenamed} />
      <div className="review-header__meta">{meta.join(" · ")}</div>
    </div>
  );
}
