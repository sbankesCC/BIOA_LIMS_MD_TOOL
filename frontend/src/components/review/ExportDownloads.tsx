// The post-export state (UI_SPEC §4.5, §5): the export just made (numbered, draft or verified)
// with its loader and audit downloads, and the run's earlier exports. Files are fetched through
// the API client and saved under their display names; storage paths are never shown.
import { useState } from "react";
import { useApiClient } from "../../api/client";
import { describeError } from "../../api/errors";
import { downloadAudit, downloadLoader } from "../../api/exports";
import type { RunExport } from "../../api/types";
import { saveFile } from "../../lib/download";
import { formatStarted } from "../../lib/format";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";

/** Props: the run, the export made on this screen (if any) and every export of the run. */
interface ExportDownloadsProps {
  runId: string;
  latest: RunExport | null;
  exports: RunExport[];
}

/** Show the latest export's downloads and the earlier exports (nothing before the first export). */
export function ExportDownloads({ runId, latest, exports }: ExportDownloadsProps) {
  const earlier = exports.filter((item) => item.export_id !== latest?.export_id).sort((a, b) => b.number - a.number);
  if (latest === null && earlier.length === 0) return null;
  return (
    <div className="export-downloads">
      {latest !== null && (
        <div className="export-downloads__latest" role="status">
          <Icon name="check" />
          <div>
            <strong>
              Export {latest.number} saved{latest.is_draft ? " as a draft (not verified)" : " (verified)"}.
            </strong>{" "}
            Both files were downloaded. Download them again here:
            <ExportFiles runId={runId} item={latest} />
          </div>
        </div>
      )}
      {earlier.length > 0 && (
        <details className="export-downloads__earlier">
          <summary>{latest !== null ? "Earlier exports" : "Exports of this run"} ({earlier.length})</summary>
          <ul>
            {earlier.map((item) => (
              <li key={item.export_id}>
                Export {item.number} · {item.is_draft ? "draft" : "verified"} · {formatStarted(item.exported_at)} by {item.exported_by}
                <ExportFiles runId={runId} item={item} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** The two download buttons of one export, labelled with the files' display names. */
function ExportFiles({ runId, item }: { runId: string; item: RunExport }) {
  const client = useApiClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Fetch one file through the API and save it under its display name
  const download = async (load: typeof downloadLoader, fileName: string) => {
    setErrorMessage(null);
    try {
      saveFile(await load(client, runId, item.export_id), fileName);
    } catch (error) {
      setErrorMessage(describeError(error));
    }
  };

  return (
    <span className="export-downloads__files">
      <button type="button" className="button-text" onClick={() => void download(downloadLoader, item.loader_file_name)}>
        Loader: {item.loader_file_name}
      </button>
      <button type="button" className="button-text" onClick={() => void download(downloadAudit, item.audit_file_name)}>
        Audit workbook: {item.audit_file_name}
      </button>
      {errorMessage !== null && <ErrorMessage message={errorMessage} />}
    </span>
  );
}
