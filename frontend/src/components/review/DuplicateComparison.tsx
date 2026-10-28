// The possible-duplicate comparison in the resolution panel (UI_SPEC §4.3): this record next
// to each existing LabVantage type the issue names, with each type's description, class and
// active flag from the run's reference data version, and this record's extracted values.
import type { DuplicateCandidate, ReviewRow, RunField } from "../../api/types";
import { describeMatch, listRecordValues, showAttribute } from "../../lib/duplicateCandidates";
import { formatShortLocation } from "../../lib/sourceLocation";
import "./DuplicateComparison.css";

/** Props of the comparison: the record, the run's fields, the existing types and the reference data version. */
interface DuplicateComparisonProps {
  row: ReviewRow | null;
  fields: RunField[];
  candidates: DuplicateCandidate[];
  referenceVersion: string | null;
}

// The existing types' attributes (reference data contract, CONTRACTS §5), one table row each
const ATTRIBUTE_ROWS: { label: string; read: (candidate: DuplicateCandidate) => string | null | undefined }[] = [
  { label: "Description", read: (candidate) => candidate.description },
  { label: "Class", read: (candidate) => candidate.consumable_class },
  { label: "Active flag", read: (candidate) => candidate.active_flag },
];

/** Show a table with this record in the first column and one column per existing type. */
export function DuplicateComparison({ row, fields, candidates, referenceVersion }: DuplicateComparisonProps) {
  if (candidates.length === 0) return null;
  const firstSource = row?.found_in[0];
  const existingSource = referenceVersion !== null ? `LabVantage (reference data ${referenceVersion})` : "LabVantage (reference data)";
  const recordValues = listRecordValues(row, fields);
  return (
    <div className="duplicate-compare">
      <div className="duplicate-compare__scroll">
        <table className="duplicate-compare__table" aria-label="Side-by-side comparison">
          <thead>
            <tr>
              <td />
              <th scope="col">This record</th>
              {candidates.map((candidate, index) => (
                <th scope="col" key={`${candidate.candidate_id}-${index}`}>
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
            {/* The existing types' attributes; this record's values sit beside them in one cell */}
            {ATTRIBUTE_ROWS.map((attribute, rowIndex) => (
              <tr key={attribute.label}>
                <th scope="row">{attribute.label}</th>
                {rowIndex === 0 && (
                  <td rowSpan={ATTRIBUTE_ROWS.length} className="duplicate-compare__record-values">
                    <RecordValues values={recordValues} />
                  </td>
                )}
                {candidates.map((candidate, index) => (
                  <td key={index}>{showAttribute(attribute.read(candidate))}</td>
                ))}
              </tr>
            ))}
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
    </div>
  );
}

/** This record's extracted values as a short list (column and value), or "—" when it has none. */
function RecordValues({ values }: { values: { column: string; value: string }[] }) {
  if (values.length === 0) return <>—</>;
  return (
    <dl className="duplicate-compare__values" aria-label="This record's values">
      {values.map((item) => (
        <div key={item.column}>
          <dt>{item.column}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
