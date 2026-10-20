// The possible-duplicate comparison in the resolution panel (UI_SPEC §4.3): this record next
// to each existing LabVantage type the issue names. Only what the API gives is shown: the
// record's name and source, each existing type's name, how it matched and the checker's reason.
import type { ReviewRow } from "../../api/types";
import { describeMatch, type DuplicateCandidate } from "../../lib/duplicateCandidates";
import { formatShortLocation } from "../../lib/sourceLocation";
import "./DuplicateComparison.css";

/** Props of the comparison: the record, the existing types and the run's reference data version. */
interface DuplicateComparisonProps {
  row: ReviewRow | null;
  candidates: DuplicateCandidate[];
  referenceVersion: string | null;
}

/** Show a table with this record in the first column and one column per existing type. */
export function DuplicateComparison({ row, candidates, referenceVersion }: DuplicateComparisonProps) {
  if (candidates.length === 0) return null;
  const firstSource = row?.found_in[0];
  const existingSource = referenceVersion !== null ? `LabVantage (reference data ${referenceVersion})` : "LabVantage (reference data)";
  return (
    <div className="duplicate-compare">
      <div className="duplicate-compare__scroll">
        <table className="duplicate-compare__table" aria-label="Side-by-side comparison">
          <thead>
            <tr>
              <td />
              <th scope="col">This record</th>
              {candidates.map((candidate, index) => (
                <th scope="col" key={`${candidate.candidateId ?? candidate.name}-${index}`}>
                  {candidates.length > 1 ? `Existing type ${index + 1}` : "Existing type"}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Names side by side */}
            <tr>
              <th scope="row">Name</th>
              <td className="duplicate-compare__name">{row?.name ?? "—"}</td>
              {candidates.map((candidate, index) => (
                <td key={index} className="duplicate-compare__name">{candidate.name}</td>
              ))}
            </tr>
            {/* Where each one comes from */}
            <tr>
              <th scope="row">Found in</th>
              <td>{firstSource !== undefined ? formatShortLocation(firstSource) : "—"}</td>
              {candidates.map((_, index) => (
                <td key={index}>{existingSource}</td>
              ))}
            </tr>
            {/* Why the check matched them */}
            <tr>
              <th scope="row">Why it matched</th>
              <td>—</td>
              {candidates.map((candidate, index) => (
                <td key={index}>{describeMatch(candidate.match)}</td>
              ))}
            </tr>
            <tr>
              <th scope="row">Checker's reason</th>
              <td>—</td>
              {candidates.map((candidate, index) => (
                <td key={index}>{candidate.reason ?? "—"}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="duplicate-compare__note">Only the name of an existing type is available here. Check its other details in LabVantage before you decide.</p>
    </div>
  );
}
