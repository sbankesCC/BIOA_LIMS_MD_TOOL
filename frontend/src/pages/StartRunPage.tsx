// The Start a run screen (landing page, UI_SPEC §4.1): run name, upload, file list, recent runs.
// Starting a run posts the files and opens the run's Processing screen.
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { startRun } from "../api/runs";
import { ErrorMessage } from "../components/ErrorMessage";
import { FileList, isUploadable, type FileEntry } from "../components/FileList";
import { Icon } from "../components/Icon";
import { RunListSection } from "../components/RunListSection";
import { UploadArea } from "../components/UploadArea";
import {
  copyFileIntoMemory,
  describeUploadLimits,
  findFileTypeLabel,
  UNREADABLE_FILE_MESSAGE,
} from "../lib/fileRules";
import { RUN_NAME_MAX_LENGTH, suggestRunName } from "../lib/runName";
import { useUploadLimits } from "../lib/useUploadLimits";
import "./StartRunPage.css";

// How many runs "Recent runs" shows; the Runs page lists them all
const RECENT_RUN_COUNT = 10;

/** Props of the screen: how to open the "How it works" popup from the intro link. */
interface StartRunPageProps {
  onOpenHowItWorks: () => void;
}

/** Show the Start a run screen. */
export function StartRunPage({ onOpenHowItWorks }: StartRunPageProps) {
  return (
    <main className="page">
      <div className="page-heading">
        <div className="eyebrow">New run</div>
        <h1>Start a new extraction</h1>
        <p className="start-run__intro">
          Upload the method, study plan and any supplemental worksheets for one study. The tool
          prepares an Excel file for review before LabVantage import. Nothing is loaded into
          LabVantage.{" "}
          <button type="button" className="start-run__link-button" onClick={onOpenHowItWorks}>
            How it works
          </button>
        </p>
      </div>
      <NewRunForm />
      <RunListSection heading="Recent runs" limit={RECENT_RUN_COUNT} />
    </main>
  );
}

/** The form: run name, upload area, file list and the Start extraction button. */
function NewRunForm() {
  const client = useApiClient();
  const navigate = useNavigate();
  const files = useFileEntries();
  const limits = useUploadLimits();
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Post the name and accepted files, then open the new run
  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = files.name.trim();
    if (name === "") {
      setSubmitError("Enter a run name, then start the extraction.");
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const started = await startRun(client, name, files.acceptedFiles);
      navigate(`/runs/${started.run_id}`);
    } catch (error) {
      setSubmitError(describeError(error));
      setIsSubmitting(false);
    }
  };

  const fileCount = files.acceptedFiles.length;
  return (
    <form className="card" aria-labelledby="new-run-heading" onSubmit={handleSubmit}>
      <h2 id="new-run-heading">1. Name the run and add documents</h2>
      <RunNameField value={files.name} onChange={files.setName} />
      <UploadArea limitPhrases={describeUploadLimits(limits)} onFilesAdded={files.addFiles} />
      {files.entries.length > 0 && (
        <div className="start-run__files">
          <div className="start-run__files-label">Files</div>
          <FileList entries={files.entries} onRemove={files.removeEntry} />
        </div>
      )}
      {submitError !== null && <ErrorMessage message={submitError} />}
      {/* Footer: how many files are ready, and the gold main action */}
      <div className="start-run__footer">
        <div className="muted">
          {fileCount === 0
            ? "Add at least one Word, PDF or Excel file to start."
            : `${fileCount} ${fileCount === 1 ? "file" : "files"} ready. Extraction usually takes a few minutes; you can leave the page while it runs.`}
        </div>
        <button
          type="submit"
          className="button-main"
          disabled={fileCount === 0 || files.isReading || isSubmitting}
        >
          {isSubmitting ? "Starting…" : "Start extraction"}
          <Icon name="arrow-right" strokeWidth={2} />
        </button>
      </div>
    </form>
  );
}

/** Props of the run name field. */
interface RunNameFieldProps {
  value: string;
  onChange: (name: string) => void;
}

/** The run name input with its hint. */
function RunNameField({ value, onChange }: RunNameFieldProps) {
  return (
    <div className="start-run__name">
      <label htmlFor="run-name">Run name</label>
      <input
        id="run-name"
        type="text"
        value={value}
        maxLength={RUN_NAME_MAX_LENGTH}
        aria-describedby="run-name-hint"
        onChange={(event) => onChange(event.target.value)}
      />
      <span id="run-name-hint" className="start-run__hint">
        Suggested from your first file and today's date. You can change it later.
      </span>
    </div>
  );
}

/** Keep the added files and the run name; the name follows the first file until edited. */
function useFileEntries() {
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [name, setTypedName] = useState("");
  const [isNameEdited, setIsNameEdited] = useState(false);
  const nextId = useRef(1);

  // Replace the entries and, unless the user typed a name, re-suggest it
  const updateEntries = (next: FileEntry[]) => {
    setEntries(next);
    if (!isNameEdited) {
      const first = next.find((entry) => entry.typeLabel !== null);
      setTypedName(first ? suggestRunName(first.file.name, new Date()) : "");
    }
  };

  // Replace one entry once its in-memory copy is made, or mark it unreadable
  const finishReading = (id: number, change: Partial<FileEntry>) => {
    setEntries((current) =>
      current.map((entry) => (entry.id === id ? { ...entry, ...change, isReading: false } : entry)),
    );
  };

  // New files are checked by type; a file already in the list is not added twice
  const addFiles = (added: File[]) => {
    const fresh = added.filter((file) => !entries.some((entry) => isSameFile(entry.file, file)));
    const newEntries: FileEntry[] = fresh.map((file) => {
      const typeLabel = findFileTypeLabel(file.name);
      return { id: nextId.current++, file, typeLabel, isReading: typeLabel !== null, readError: null };
    });
    updateEntries([...entries, ...newEntries]);
    // Copy each accepted file into memory now: Chrome refuses to upload a picked file that
    // changed on disk afterwards (open in Word or Excel, or syncing to OneDrive)
    for (const entry of newEntries.filter((item) => item.isReading)) {
      copyFileIntoMemory(entry.file).then(
        (copy) => finishReading(entry.id, { file: copy }),
        () => finishReading(entry.id, { readError: UNREADABLE_FILE_MESSAGE }),
      );
    }
  };

  const removeEntry = (id: number) => updateEntries(entries.filter((entry) => entry.id !== id));

  // Typing a name stops the suggestion from replacing it
  const setName = (typed: string) => {
    setTypedName(typed);
    setIsNameEdited(true);
  };

  // Only readable files of an accepted type are sent; Start waits until every copy is made
  const acceptedFiles = entries.filter(isUploadable).map((entry) => entry.file);
  const isReading = entries.some((entry) => entry.isReading);
  return { entries, acceptedFiles, isReading, name, setName, addFiles, removeEntry };
}

/** Return true when two files look like the same file (same name, size and date). */
function isSameFile(first: File, second: File): boolean {
  return (
    first.name === second.name &&
    first.size === second.size &&
    first.lastModified === second.lastModified
  );
}
