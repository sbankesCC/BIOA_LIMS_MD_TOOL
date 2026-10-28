// The admin screens' upload card (UI_SPEC §4.6): choose a file, then the check report
// (passed checks, problems, warnings, changes by list) and "Apply updates as vN", which is
// disabled with the reason while problems remain. Warnings never block the apply.
import { useRef, type ChangeEvent } from "react";
import type { DataVersionList, UploadFinding } from "../../api/types";
import { describeApplyBlock, findNextVersionName, isLookupReport, type AdminKind } from "../../lib/adminVersions";
import type { AdminData, AdminUpload } from "../../lib/useAdminData";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";
import { ChangesTable } from "./ChangesTable";

// The file types each upload accepts (the API checks the file itself)
const ACCEPTED_FILES: Record<AdminKind, string> = {
  lookup: ".xlsx",
  reference: ".xlsx,.csv",
};

// What the user is asked to upload in each section
const UPLOAD_HINTS: Record<AdminKind, string> = {
  lookup: "Download the current workbook, edit the lists, then upload it here. Nothing changes until you apply it.",
  reference: "Upload an export of the existing Consumable Types (.xlsx or .csv). Nothing changes until you apply it.",
};

/** Props of the upload card. */
interface UploadCardProps {
  kind: AdminKind;
  data: AdminData;
  versions: DataVersionList;
}

/** Show the upload area and, after an upload, its check report and the Apply button. */
export function UploadCard({ kind, data, versions }: UploadCardProps) {
  const input = useRef<HTMLInputElement>(null);
  const upload = data.upload;

  // A picked file is uploaded at once; the input is cleared so the same file can be picked again
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file !== undefined) void data.uploadFile(file);
  };

  return (
    <section className="card" aria-labelledby="admin-upload-heading">
      <h2 id="admin-upload-heading">Upload a new version</h2>
      {/* The chosen file (or a prompt), with the button that opens the file picker */}
      <div className="admin-file">
        <span className="admin-file__icon">
          <Icon name="file" size={22} strokeWidth={1.6} />
        </span>
        <div className="admin-file__text">
          <div className="admin-file__name">{upload !== null ? upload.fileName : "No file uploaded yet"}</div>
          <div className="muted admin-file__meta">{data.isBusy && upload === null ? "Checking…" : upload !== null ? "Checked just now" : UPLOAD_HINTS[kind]}</div>
        </div>
        <button type="button" className="button-secondary" disabled={data.isBusy} onClick={() => input.current?.click()}>
          {upload !== null ? "Upload a different file" : "Choose a file"}
        </button>
        <input ref={input} type="file" accept={ACCEPTED_FILES[kind]} className="visually-hidden" tabIndex={-1} aria-label="File to upload" onChange={handleChange} />
      </div>
      {upload !== null && <UploadReportView kind={kind} upload={upload} />}
      {upload !== null && <ApplyBar data={data} upload={upload} versions={versions} />}
      {data.actionError !== null && <ErrorMessage message={data.actionError} />}
    </section>
  );
}

/** The check report: checks, problems and warnings on the left, changes on the right. */
function UploadReportView({ kind, upload }: { kind: AdminKind; upload: AdminUpload }) {
  const report = upload.report;
  return (
    <div className="admin-report">
      <div className="admin-report__checks">
        <h3>Checks</h3>
        {!isLookupReport(report) && <p className="muted admin-report__rows">Rows read: {report.row_count}</p>}
        {report.passed_checks.map((check) => (
          <div key={check} className="admin-report__passed">
            <Icon name="check" strokeWidth={2.2} /> {check}
          </div>
        ))}
        <FindingList tone="problem" findings={report.problems} />
        <FindingList tone="warning" findings={report.warnings} />
      </div>
      {kind === "lookup" && isLookupReport(report) && (
        <div className="admin-report__changes">
          <h3>Changes from {report.current_version}</h3>
          <ChangesTable changes={report.changes} />
        </div>
      )}
    </div>
  );
}

/** A box of problems (red: must be fixed) or warnings (amber: do not block), each with sheet and row. */
function FindingList({ tone, findings }: { tone: "problem" | "warning"; findings: UploadFinding[] }) {
  if (findings.length === 0) return null;
  const count = findings.length;
  const heading =
    tone === "problem"
      ? `${count} ${count === 1 ? "problem" : "problems"} to fix before applying`
      : `${count} ${count === 1 ? "warning" : "warnings"}: these do not stop the update`;
  return (
    <div className={`admin-findings admin-findings--${tone}`} role="group" aria-label={heading}>
      <div className="admin-findings__heading">
        <Icon name={tone === "problem" ? "cross-circle" : "warning"} strokeWidth={2} /> {heading}
      </div>
      <ul className="admin-findings__list">
        {findings.map((finding, index) => (
          <li key={`${finding.code}-${index}`}>
            <FindingPlace finding={finding} />
            {finding.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The bold sheet name and the row of a finding, when the report gives them. */
function FindingPlace({ finding }: { finding: UploadFinding }) {
  if (finding.sheet == null && finding.row == null) return null;
  return (
    <>
      {finding.sheet != null && <strong>{finding.sheet}</strong>}
      {finding.row != null && `${finding.sheet != null ? ", " : ""}row ${finding.row}`}
      {": "}
    </>
  );
}

/** "Apply updates as vN", disabled with the reason while the upload has problems. */
function ApplyBar({ data, upload, versions }: { data: AdminData; upload: AdminUpload; versions: DataVersionList }) {
  const block = describeApplyBlock(upload.report, upload.pending);
  return (
    <div className="admin-apply">
      {block !== null && (
        <span id="admin-apply-why" className="admin-apply__why">
          {block}
        </span>
      )}
      <button
        type="button"
        className="admin-button"
        disabled={block !== null || data.isBusy}
        aria-describedby={block !== null ? "admin-apply-why" : undefined}
        onClick={() => void data.applyUpload()}
      >
        Apply updates as {findNextVersionName(versions)}
      </button>
    </div>
  );
}
