// The diff of a lookup list upload: values added and removed per list, and a toggle
// "View every added and removed value" that lists them all.
import { useState } from "react";
import type { SheetChange } from "../../api/types";

/** Props of the table: the changes by sheet from the check report. */
interface ChangesTableProps {
  changes: SheetChange[];
}

/** Show the added and removed counts per list, and every value on request. */
export function ChangesTable({ changes }: ChangesTableProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  if (changes.length === 0) {
    return <p className="muted">No values added or removed.</p>;
  }
  return (
    <>
      <div className="admin-table__scroll">
        <table className="admin-table">
          <thead>
            <tr>
              <th scope="col">List</th>
              <th scope="col">Added</th>
              <th scope="col">Removed</th>
            </tr>
          </thead>
          <tbody>
            {changes.map((change) => (
              <tr key={change.sheet}>
                <td>
                  {change.sheet}
                  {change.is_new_sheet === true && <span className="muted"> (new list)</span>}
                  {change.is_removed_sheet === true && <span className="muted"> (list removed)</span>}
                </td>
                <td>{change.added.length}</td>
                <td>{change.removed.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className="button-text admin-changes__toggle" aria-expanded={isExpanded} onClick={() => setIsExpanded(!isExpanded)}>
        {isExpanded ? "Hide the added and removed values" : "View every added and removed value"}
      </button>
      {isExpanded && <AllValues changes={changes} />}
    </>
  );
}

/** Every added and removed value, list by list. */
function AllValues({ changes }: ChangesTableProps) {
  return (
    <div className="admin-changes__all" aria-label="Every added and removed value">
      {changes.map((change) => (
        <div key={change.sheet} className="admin-changes__sheet">
          <h4>{change.sheet}</h4>
          {change.added.length > 0 && <ValueLine label="Added" values={change.added} />}
          {change.removed.length > 0 && <ValueLine label="Removed" values={change.removed} />}
        </div>
      ))}
    </div>
  );
}

/** One line "Added: a; b; c" with each value quoted so spaces show. */
function ValueLine({ label, values }: { label: string; values: string[] }) {
  return (
    <p className="admin-changes__values">
      <span className="admin-changes__label">{label}:</span> {values.map((value) => `“${value}”`).join("; ")}
    </p>
  );
}
