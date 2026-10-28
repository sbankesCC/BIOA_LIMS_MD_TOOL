// A card listing runs: loading text, an error, an empty message, or the runs table.
// The Start screen shows the newest few; the Runs page shows them all.
import { Link } from "react-router-dom";
import { useRunList } from "../lib/useRunList";
import { ErrorMessage } from "./ErrorMessage";
import { RunsTable } from "./RunsTable";

/** Props of the section: its heading and, for Recent runs, how many runs to show. */
interface RunListSectionProps {
  heading: string;
  limit?: number;
}

/** Load the runs and show them in a card under a heading. */
export function RunListSection({ heading, limit }: RunListSectionProps) {
  const { runs, errorMessage } = useRunList();
  const shownRuns = runs && limit !== undefined ? runs.slice(0, limit) : runs;
  const hasMore = runs !== null && limit !== undefined && runs.length > limit;

  return (
    <section className="card" aria-labelledby="run-list-heading">
      <h2 id="run-list-heading">{heading}</h2>
      {/* One of: error, loading, empty, or the table */}
      {errorMessage !== null && <ErrorMessage message={errorMessage} />}
      {errorMessage === null && shownRuns === null && <p className="muted">Loading runs…</p>}
      {shownRuns !== null && shownRuns.length === 0 && (
        <p className="muted">No runs yet.</p>
      )}
      {shownRuns !== null && shownRuns.length > 0 && <RunsTable runs={shownRuns} />}
      {hasMore && <Link to="/runs">See all runs</Link>}
    </section>
  );
}
