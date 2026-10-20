// The read-only records grid (UI_SPEC §4.3): Action needed, the record name and Found in are
// first (the first two pinned), then one column per field. Clicking a value opens the panel;
// clicking Found in opens the source. Arrow keys move between the clickable cells.
import { Fragment, type KeyboardEvent, type ReactNode } from "react";
import type { ReviewCell, ReviewRow, RunField, SourceLocation } from "../../api/types";
import { describeCell } from "../../lib/cellDisplay";
import { findCell } from "../../lib/reviewIssues";
import { formatLocation } from "../../lib/sourceLocation";
import { Icon } from "../Icon";
import { ActionNeededLabel } from "./ActionNeeded";
import "./RecordsGrid.css";

// Header of the pinned name column when the name field cannot be told from the data
const FALLBACK_NAME_HEADER = "Name";

/** Props of the grid: rows, fields, the name field, the selection and the click handlers. */
interface RecordsGridProps {
  rows: ReviewRow[];
  fields: RunField[];
  nameField: string | null;
  selectedRecordId: string | null;
  selectedField: string | null;
  onOpenCell: (row: ReviewRow, cell: ReviewCell) => void;
  onOpenFoundIn: (row: ReviewRow) => void;
  // M13: e.g. the Restore link of an excluded row
  renderExclusionAction?: (row: ReviewRow) => ReactNode;
}

/** Show the records as a scrolling table with a sticky header and pinned columns. */
export function RecordsGrid(props: RecordsGridProps) {
  const { rows, fields, nameField } = props;
  const nameColumn = fields.find((field) => field.key === nameField)?.column ?? FALLBACK_NAME_HEADER;
  const otherFields = fields.filter((field) => field.key !== nameField);
  return (
    <div className="records-grid__scroll" tabIndex={-1}>
      <table className="records-grid" onKeyDown={moveFocusWithArrows}>
        <thead>
          <tr>
            <th scope="col" className="records-grid__pin records-grid__pin--action">Action needed</th>
            <th scope="col" className="records-grid__pin records-grid__pin--name">{nameColumn}</th>
            <th scope="col">Found in</th>
            {otherFields.map((field) => (
              <th scope="col" key={field.key}>{field.column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <GridRow key={row.record_id} {...props} row={row} rowIndex={rowIndex} otherFields={otherFields} />
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="records-grid__empty muted">No records match this filter.</p>}
    </div>
  );
}

/** Props of one row: the grid's props plus the row, its position and the field columns. */
interface GridRowProps extends RecordsGridProps {
  row: ReviewRow;
  rowIndex: number;
  otherFields: RunField[];
}

/** One record: action needed, name, Found in, then its values (or the exclusion reason). */
function GridRow({ row, rowIndex, otherFields, fields, nameField, selectedRecordId, selectedField, onOpenCell, onOpenFoundIn, renderExclusionAction }: GridRowProps) {
  const isSelected = row.record_id === selectedRecordId;
  const isExcluded = row.exclusion !== null;
  const nameCell = nameField !== null ? findCell(row, nameField) : null;
  const fieldByKey = new Map(fields.map((field) => [field.key, field]));
  const rowClass = ["records-grid__row", isSelected ? "records-grid__row--selected" : "", isExcluded ? "records-grid__row--excluded" : ""].join(" ");
  // Cells after the pinned ones and Found in start at column 3
  const renderValue = (cell: ReviewCell | null, column: number) => (
    <ValueCell
      cell={cell}
      field={cell !== null ? fieldByKey.get(cell.field) ?? null : null}
      rowIndex={rowIndex}
      column={column}
      isSelected={isSelected && cell !== null && cell.field === selectedField}
      isClickable={!isExcluded}
      onOpen={() => cell !== null && onOpenCell(row, cell)}
    />
  );
  return (
    <tr className={rowClass} aria-selected={isSelected}>
      <td className="records-grid__pin records-grid__pin--action">
        <ActionNeededLabel action={row.action_needed} />
      </td>
      {nameCell !== null ? (
        renderValue(nameCell, 1)
      ) : (
        <td className="records-grid__pin records-grid__pin--name records-grid__name">{row.name ?? "—"}</td>
      )}
      <td className="records-grid__found-in">
        <FoundIn locations={row.found_in} rowIndex={rowIndex} onOpen={() => onOpenFoundIn(row)} />
      </td>
      {isExcluded ? (
        <td colSpan={otherFields.length} className="records-grid__exclusion">
          Excluded by {row.exclusion?.by}: {row.exclusion?.reason}
          {renderExclusionAction?.(row)}
        </td>
      ) : (
        otherFields.map((field, index) => <Fragment key={field.key}>{renderValue(findCell(row, field.key), index + 3)}</Fragment>)
      )}
    </tr>
  );
}

/** Props of a value cell. */
interface ValueCellProps {
  cell: ReviewCell | null;
  field: RunField | null;
  rowIndex: number;
  column: number;
  isSelected: boolean;
  isClickable: boolean;
  onOpen: () => void;
}

/** One value: tinted by its issues, with "as written → exported" when they differ. */
function ValueCell({ cell, field, rowIndex, column, isSelected, isClickable, onOpen }: ValueCellProps) {
  const pinClass = column === 1 ? " records-grid__pin records-grid__pin--name records-grid__name" : "";
  if (cell === null) {
    return <td className={pinClass.trim()} />;
  }
  const display = describeCell(cell, field);
  const tdClass = `records-grid__cell records-grid__cell--${cell.color}${isSelected ? " records-grid__cell--selected" : ""}${pinClass}`;
  const content = <CellContent display={display} color={cell.color} />;
  // Placeholder values and excluded rows are not clickable
  if (display.look === "placeholder" || !isClickable) {
    return <td className={tdClass}>{content}</td>;
  }
  return (
    <td className={tdClass}>
      <button
        type="button"
        className="records-grid__value"
        data-grid-row={rowIndex}
        data-grid-col={column}
        aria-label={describeCellForReaders(cell.column, display.text, display.writtenText, cell.color)}
        onClick={onOpen}
      >
        {content}
      </button>
    </td>
  );
}

/** The visible text of a cell: an issue icon, the value as written and the exported value. */
function CellContent({ display, color }: { display: ReturnType<typeof describeCell>; color: ReviewCell["color"] }) {
  return (
    <span className={`records-grid__text records-grid__text--${display.look}`}>
      {color === "red" && <Icon name="cross-circle" size={14} strokeWidth={2} />}
      {color === "yellow" && <Icon name="warning" size={14} strokeWidth={2} />}
      {display.writtenText !== null && (
        <>
          <span className="records-grid__written">“{display.writtenText}”</span>
          <span aria-hidden="true"> → </span>
        </>
      )}
      <span>{display.text}</span>
    </span>
  );
}

/** Return the label a screen reader hears for a value cell. */
function describeCellForReaders(column: string, text: string, written: string | null, color: ReviewCell["color"]): string {
  const parts = [`${column}: ${text}`];
  if (written !== null) parts.push(`written as ${written}`);
  if (color === "red") parts.push("needs a fix");
  if (color === "yellow") parts.push("check");
  return parts.join(", ");
}

/** The Found in link: the first location, "+N more" when several; opens the source. */
function FoundIn({ locations, rowIndex, onOpen }: { locations: SourceLocation[]; rowIndex: number; onOpen: () => void }) {
  const first = locations[0];
  if (first === undefined) {
    return <span className="muted">No source recorded</span>;
  }
  return (
    <button type="button" className="records-grid__link" data-grid-row={rowIndex} data-grid-col={2} onClick={onOpen}>
      <Icon name="file" size={15} />
      <span className="records-grid__link-text">{formatLocation(first)}</span>
      {first.is_scanned && <span className="muted"> (scan)</span>}
      {locations.length > 1 && <span className="muted"> +{locations.length - 1} more</span>}
    </button>
  );
}

// Arrow keys and the row and column steps they move by
const ARROW_STEPS: Record<string, [number, number]> = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

// How far an arrow looks for the next clickable cell (skipping blank or read-only ones)
const MAX_ARROW_REACH = 200;

/** Move focus to the next clickable cell in the arrow's direction. */
function moveFocusWithArrows(event: KeyboardEvent<HTMLTableElement>) {
  const step = ARROW_STEPS[event.key];
  const current = event.target as HTMLElement;
  if (step === undefined || current.dataset.gridRow === undefined) {
    return;
  }
  let row = Number(current.dataset.gridRow);
  let column = Number(current.dataset.gridCol);
  // Walk in the arrow's direction until a clickable cell is found
  for (let reach = 0; reach < MAX_ARROW_REACH; reach += 1) {
    row += step[0];
    column += step[1];
    if (row < 0 || column < 0) return;
    const next = event.currentTarget.querySelector<HTMLElement>(`[data-grid-row="${row}"][data-grid-col="${column}"]`);
    if (next !== null) {
      event.preventDefault();
      next.focus();
      return;
    }
  }
}
