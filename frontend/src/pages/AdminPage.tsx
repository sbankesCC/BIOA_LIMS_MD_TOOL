// The Admin screens (UI_SPEC §4.6, §4.7): Lookup lists and Reference data, each with the
// current version card, an upload with its check report, Apply, and the version history.
import { NavLink } from "react-router-dom";
import { CurrentVersionCard } from "../components/admin/CurrentVersionCard";
import { UploadCard } from "../components/admin/UploadCard";
import { VersionHistory } from "../components/admin/VersionHistory";
import { ErrorMessage } from "../components/ErrorMessage";
import type { AdminKind } from "../lib/adminVersions";
import { useAdminData } from "../lib/useAdminData";
import "../components/admin/Admin.css";

// The page title of each admin section
const TITLES: Record<AdminKind, string> = {
  lookup: "Lookup lists",
  reference: "Reference data",
};

/** Props of the admin page: which section it shows. */
interface AdminPageProps {
  kind: AdminKind;
}

/** Show one admin section; a new key resets its state when the user switches sections. */
export function AdminPage({ kind }: AdminPageProps) {
  return (
    <main className="page admin-page">
      <div className="page-heading">
        <div className="eyebrow">Admin</div>
        <h1>{TITLES[kind]}</h1>
        <AdminTabs />
      </div>
      <AdminSection key={kind} kind={kind} />
    </main>
  );
}

/** The two section pills: Lookup lists and Reference data. */
function AdminTabs() {
  const makeClass = ({ isActive }: { isActive: boolean }) => (isActive ? "admin-tabs__tab admin-tabs__tab--active" : "admin-tabs__tab");
  return (
    <nav aria-label="Admin sections" className="admin-tabs">
      <NavLink to="/admin" end className={makeClass}>
        Lookup lists
      </NavLink>
      <NavLink to="/admin/reference-data" className={makeClass}>
        Reference data
      </NavLink>
    </nav>
  );
}

/** The cards of one section, or a plain message when the user has no admin access. */
function AdminSection({ kind }: AdminPageProps) {
  const data = useAdminData(kind);
  // The API refused an admin call (403): say so plainly, nothing else is shown
  if (data.isForbidden) {
    return (
      <section className="card" aria-label="No access">
        <h2>You do not have access to the admin screens</h2>
        <p className="muted">Lookup lists and reference data can only be changed by an admin. Ask an admin to make this change, or to give you the admin role.</p>
      </section>
    );
  }
  return (
    <>
      {data.loadError !== null && <ErrorMessage message={data.loadError} />}
      {data.notice !== null && (
        <p className="admin-notice" role="status">
          {data.notice}
        </p>
      )}
      {data.versions !== null && <CurrentVersionCard kind={kind} data={data} versions={data.versions} />}
      {data.versions !== null && <UploadCard kind={kind} data={data} versions={data.versions} />}
      {data.versions !== null && <VersionHistory kind={kind} data={data} versions={data.versions} />}
      {data.versions === null && data.loadError === null && <p className="muted">Loading versions…</p>}
    </>
  );
}
