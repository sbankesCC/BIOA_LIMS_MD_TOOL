// The admin screens' current version card: the version new runs use, who uploaded it and when,
// and (lookup lists only) "Download current workbook". Reference data has no download endpoint.
import type { DataVersionList } from "../../api/types";
import { describeVersionChanges, findCurrentVersion, formatVersionDate, type AdminKind } from "../../lib/adminVersions";
import type { AdminData } from "../../lib/useAdminData";
import { Icon } from "../Icon";

/** Props of the card: the section, its data and actions, and its version history. */
interface CurrentVersionCardProps {
  kind: AdminKind;
  data: AdminData;
  versions: DataVersionList;
}

/** Show the current version with its upload details. */
export function CurrentVersionCard({ kind, data, versions }: CurrentVersionCardProps) {
  const current = findCurrentVersion(versions);
  return (
    <section className="card admin-current" aria-labelledby="admin-current-heading">
      <div className="admin-current__text">
        <h2 id="admin-current-heading">{describeHeading(kind, versions.current_version)}</h2>
        <div className="muted">{describeMeta(kind, versions.current_version, current)}</div>
      </div>
      {kind === "lookup" && (
        <button type="button" className="admin-button" disabled={data.isBusy} onClick={() => void data.downloadCurrent()}>
          <Icon name="download" /> Download current workbook
        </button>
      )}
    </section>
  );
}

/** Return the card heading: the current version, or that none was applied yet. */
function describeHeading(kind: AdminKind, versionId: string | null): string {
  if (versionId === null) {
    return kind === "reference" ? "No reference data yet" : "No current version";
  }
  return `Current version: ${versionId}`;
}

/** Return the line under the heading: who uploaded the current version, when, and its size. */
function describeMeta(kind: AdminKind, versionId: string | null, current: ReturnType<typeof findCurrentVersion>): string {
  // Nothing applied yet: reference data starts empty; lookup lists start from the client's own file
  if (current === null) {
    if (kind === "reference") {
      return "Upload an export of the existing Consumable Types so new runs can check for duplicates.";
    }
    return versionId !== null ? "The starting lists that come with the tool. No upload has been applied yet." : "";
  }
  return [
    `Uploaded by ${current.uploaded_by}`,
    formatVersionDate(current.uploaded_at),
    current.file_name,
    describeVersionChanges(current, kind),
  ].join(" · ");
}
