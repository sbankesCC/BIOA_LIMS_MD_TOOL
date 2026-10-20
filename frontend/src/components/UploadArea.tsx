// The upload area of the Start screen: drag and drop, or "Browse files" (UI_SPEC §4.1).
// It only hands files to its parent; the parent checks types and keeps the list.
import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { ACCEPT_ATTRIBUTE } from "../lib/fileRules";
import { Icon } from "./Icon";
import "./UploadArea.css";

/** Props of the upload area: what to do with the files the user adds. */
interface UploadAreaProps {
  onFilesAdded: (files: File[]) => void;
}

/** Show a drop zone with a "Browse files" button. */
export function UploadArea({ onFilesAdded }: UploadAreaProps) {
  const input = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  // Files picked with the browse dialog; the input is cleared so the same file can be picked again
  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const picked = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (picked.length > 0) {
      onFilesAdded(picked);
    }
  };

  // Files dropped on the area
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOver(false);
    const dropped = Array.from(event.dataTransfer.files);
    if (dropped.length > 0) {
      onFilesAdded(dropped);
    }
  };

  // Allow dropping and show the hover state while files are dragged over
  const handleDragOver = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOver(true);
  };

  return (
    <div
      className={isDragOver ? "upload-area upload-area--over" : "upload-area"}
      onDragOver={handleDragOver}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={handleDrop}
    >
      <span className="upload-area__icon">
        <Icon name="upload" size={36} strokeWidth={1.6} />
      </span>
      <div className="upload-area__title">Drag files here</div>
      <div className="muted">Word (.docx), PDF or Excel (.xlsx)</div>
      <button type="button" className="button-secondary" onClick={() => input.current?.click()}>
        Browse files
      </button>
      {/* The real file input stays hidden; the button opens it */}
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT_ATTRIBUTE}
        className="visually-hidden"
        tabIndex={-1}
        aria-label="Add files"
        onChange={handleChange}
      />
    </div>
  );
}
