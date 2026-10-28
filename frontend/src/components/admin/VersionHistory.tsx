// The admin screens' version history: version, uploaded by, date, changes, Current or
// Superseded, Download (lookup lists only) and "Restore vN" with a confirmation dialog.
import { useState } from "react";
import type { DataVersionInfo, DataVersionList } from "../../api/types";
import { describeVersionChanges, formatVersionDate, listAppliedVersions, type AdminKind } from "../../lib/adminVersions";
import type { AdminData } from "../../lib/useAdminData";
import { Dialog } from "../Dialog";

/** Props of the history card. */
interface VersionHistoryProps {
  kind: AdminKind;
  data: AdminData;
  versions: DataVersionList;
}

/** Show every applied version, newest first, with Download and Restore. */
export function VersionHistory({ kind, data, versions }: VersionHistoryProps) {
  const [restoring, setRestoring] = useState<string | null>(null);
  const applied = listAppliedVersions(versions);
  return (
    <section className="card" aria-labelledby="admin-history-heading">
      <h2 id="admin-history-heading">Version history</h2>
      {applied.length === 0 ? (
        <p className="muted">No version has been applied yet.</p>
      ) : (
        <div className="admin-table__scroll">
          <table className="admin-table admin-table--history">
            <thead>
              <tr>
                <th scope="col">Version</th>
                <th scope="col">Uploaded by</th>
                <th scope="col">Date</th>
                <th scope="col">Changes</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="visually-hidden">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {applied.map((version) => (
                <HistoryRow key={version.upload_id} kind={kind} data={data} version={version} onRestore={setRestoring} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {restoring !== null && (
        <RestoreDialog
          versionId={restoring}
          onCancel={() => setRestoring(null)}
          onConfirm={() => {
            setRestoring(null);
            void data.restoreVersion(restoring);
          }}
        />
      )}
    </section>
  );
}

/** One version row. */
function HistoryRow({ kind, data, version, onRestore }: { kind: AdminKind; data: AdminData; version: DataVersionInfo; onRestore: (versionId: string) => void }) {
  const versionId = version.version_id ?? version.upload_id;
  const isCurrent = version.status === "current";
  return (
    <tr>
      <td className="admin-table__version">{versionId}</td>
      <td>{version.uploaded_by}</td>
      <td>{formatVersionDate(version.uploaded_at)}</td>
      <td>{describeVersionChanges(version, kind)}</td>
      <td>
        <span className={isCurrent ? "admin-status admin-status--current" : "admin-status"}>{isCurrent ? "Current" : "Superseded"}</span>
      </td>
      <td>
        <div className="admin-table__actions">
          {kind === "lookup" && (
            <button type="button" className="button-text admin-link" disabled={data.isBusy} onClick={() => void data.downloadVersion(versionId)}>
              Download
            </button>
          )}
          {!isCurrent && (
            <button type="button" className="button-text admin-link" disabled={data.isBusy} onClick={() => onRestore(versionId)}>
              Restore {versionId}
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

/** Ask before restoring: new runs will use the restored version. */
function RestoreDialog({ versionId, onCancel, onConfirm }: { versionId: string; onCancel: () => void; onConfirm: () => void }) {
  return (
    <Dialog
      title={`Restore ${versionId}?`}
      onClose={onCancel}
      actions={
        <>
          <button type="button" className="button-secondary" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="dialog__primary" onClick={onConfirm}>
            Restore {versionId}
          </button>
        </>
      }
    >
      <p>
        {versionId} becomes the current version again. New runs use it; runs already started keep the version they started with.
      </p>
    </Dialog>
  );
}
