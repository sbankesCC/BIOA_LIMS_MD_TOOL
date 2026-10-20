// The list of files added on the Start screen: name, type and size, with a remove button.
// Refused files stay in the list with a short reason until dismissed (as in the mockup).
import { formatFileSize } from "../lib/format";
import { REJECTED_FILE_MESSAGE } from "../lib/fileRules";
import { Icon } from "./Icon";
import "./FileList.css";

/** One entry in the list: the file and its type label, or null when the type is refused. */
export interface FileEntry {
  id: number;
  file: File;
  typeLabel: string | null;
}

/** Props of the list: the entries and what removing one does. */
interface FileListProps {
  entries: FileEntry[];
  onRemove: (id: number) => void;
}

/** Show each added file, accepted or refused, with a button to remove it. */
export function FileList({ entries, onRemove }: FileListProps) {
  return (
    <ul className="file-list" aria-label="Files">
      {entries.map((entry) =>
        entry.typeLabel === null ? (
          <RejectedFileItem key={entry.id} entry={entry} onRemove={onRemove} />
        ) : (
          <AcceptedFileItem key={entry.id} entry={entry} onRemove={onRemove} />
        ),
      )}
    </ul>
  );
}

/** Props of one list item. */
interface FileItemProps {
  entry: FileEntry;
  onRemove: (id: number) => void;
}

/** Show an accepted file: icon, name, type and size, and Remove. */
function AcceptedFileItem({ entry, onRemove }: FileItemProps) {
  return (
    <li className="file-list__item">
      <span className="file-list__icon">
        <Icon name="file" size={22} strokeWidth={1.6} />
      </span>
      <div className="file-list__text">
        <div className="file-list__name">{entry.file.name}</div>
        <div className="file-list__meta">
          {entry.typeLabel} · {formatFileSize(entry.file.size)}
        </div>
      </div>
      <button
        type="button"
        className="file-list__remove"
        aria-label={`Remove ${entry.file.name}`}
        onClick={() => onRemove(entry.id)}
      >
        <Icon name="close" />
      </button>
    </li>
  );
}

/** Show a refused file in red with the reason, and Dismiss. */
function RejectedFileItem({ entry, onRemove }: FileItemProps) {
  return (
    <li className="file-list__item file-list__item--rejected">
      <span className="file-list__icon">
        <Icon name="cross-circle" size={22} />
      </span>
      <div className="file-list__text">
        <div className="file-list__name">{entry.file.name}</div>
        <div className="file-list__meta">{REJECTED_FILE_MESSAGE}</div>
      </div>
      <button
        type="button"
        className="file-list__remove"
        aria-label={`Dismiss ${entry.file.name}`}
        onClick={() => onRemove(entry.id)}
      >
        <Icon name="close" />
      </button>
    </li>
  );
}
