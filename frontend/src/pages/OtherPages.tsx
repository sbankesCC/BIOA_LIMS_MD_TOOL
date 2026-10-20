// Small screens around the main ones: the Runs list, the Admin placeholder, the run and
// review route wrappers and "page not found". The Admin screens come in a later milestone.
import { Link, useParams } from "react-router-dom";
import { RunListSection } from "../components/RunListSection";
import { ReviewWithActions } from "../components/review/ReviewExtensions";
import { ProcessingPage } from "./ProcessingPage";

/** Show every run, newest first. */
export function RunsPage() {
  return (
    <main className="page">
      <div className="page-heading">
        <div className="eyebrow">Runs</div>
        <h1>Runs</h1>
      </div>
      <RunListSection heading="All runs" />
    </main>
  );
}

/** Open a run from its address; a new key resets the screen when the run changes (Retry). */
export function RunRoute() {
  const { runId = "" } = useParams();
  return <ProcessingPage key={runId} runId={runId} />;
}

/** Open a run's Review screen (with bulk actions, Verify and export); a new key resets it for another run. */
export function ReviewRoute() {
  const { runId = "" } = useParams();
  return <ReviewWithActions key={runId} runId={runId} />;
}

/** Admin placeholder until the lookup list and reference data screens are built. */
export function AdminPage() {
  return (
    <main className="page">
      <div className="page-heading">
        <div className="eyebrow">Admin</div>
        <h1>Admin</h1>
        <p>The lookup list and reference data screens are not available yet.</p>
      </div>
    </main>
  );
}

/** Shown for an address the app does not know. */
export function NotFoundPage() {
  return (
    <main className="page">
      <div className="page-heading">
        <h1>Page not found</h1>
        <p>
          This address does not match a page. <Link to="/">Start a new run</Link> or open{" "}
          <Link to="/runs">Runs</Link>.
        </p>
      </div>
    </main>
  );
}
