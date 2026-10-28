// The source viewer: shows a cited chunk's text with the quoted passage highlighted, or the
// scanned page image for a page_image chunk (GET /runs/{id}/chunks/{chunk_id} and /image).
// Several locations (e.g. "+1 more") are listed as buttons above the text.
import { useEffect, useRef, useState } from "react";
import { useApiClient } from "../../api/client";
import { describeError } from "../../api/errors";
import { getChunk, getChunkImage } from "../../api/review";
import type { CellSource, ChunkSource, SourceLocation } from "../../api/types";
import { findQuoteRange, splitIntoSegments, type TextRange } from "../../lib/highlight";
import { formatLocation } from "../../lib/sourceLocation";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";
import "./SourceViewer.css";

/** What to show: the locations, the quotes to highlight in each chunk, and the first one shown. */
export interface SourceRequest {
  title: string;
  locations: SourceLocation[];
  quotesByChunk: Record<string, string[]>;
  startIndex: number;
}

/** Build a request from evidence pairs (one location per chunk, its quotes collected). */
export function makeSourceRequest(title: string, sources: CellSource[], locations: SourceLocation[] = []): SourceRequest {
  const quotesByChunk: Record<string, string[]> = {};
  const byChunk = new Map<string, SourceLocation>();
  // Locations given first keep their order; evidence adds its chunks and quotes
  for (const location of locations) {
    byChunk.set(location.chunk_id, location);
  }
  for (const source of sources) {
    byChunk.set(source.location.chunk_id, byChunk.get(source.location.chunk_id) ?? source.location);
    quotesByChunk[source.location.chunk_id] = [...(quotesByChunk[source.location.chunk_id] ?? []), source.quote];
  }
  return { title, locations: [...byChunk.values()], quotesByChunk, startIndex: 0 };
}

/** Props of the viewer: the run, what to show, and what closing does. */
interface SourceViewerProps {
  runId: string;
  request: SourceRequest;
  onClose: () => void;
}

/** Show a source dialog; Escape or the X closes it. */
export function SourceViewer({ runId, request, onClose }: SourceViewerProps) {
  const [index, setIndex] = useState(request.startIndex);
  const closeButton = useRef<HTMLButtonElement>(null);
  const location = request.locations[index];

  // Focus the close button on open, and close on Escape
  useEffect(() => {
    closeButton.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  return (
    <div className="source-viewer__backdrop" onClick={onClose}>
      <div
        className="source-viewer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-viewer-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="source-viewer__header">
          <div>
            <div className="eyebrow">Source</div>
            <h2 id="source-viewer-title">{request.title}</h2>
          </div>
          <button ref={closeButton} type="button" className="icon-button" aria-label="Close source" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        {request.locations.length > 1 && (
          <LocationPicker locations={request.locations} index={index} onPick={setIndex} />
        )}
        {location === undefined ? (
          <p className="muted">No source was recorded for this value.</p>
        ) : (
          <ChunkView key={location.chunk_id} runId={runId} location={location} quotes={request.quotesByChunk[location.chunk_id] ?? []} />
        )}
      </div>
    </div>
  );
}

/** Buttons for each location when there are several. */
function LocationPicker({ locations, index, onPick }: { locations: SourceLocation[]; index: number; onPick: (index: number) => void }) {
  return (
    <div className="source-viewer__locations" role="group" aria-label="Source locations">
      {locations.map((location, position) => (
        <button
          key={location.chunk_id}
          type="button"
          className="source-viewer__location"
          aria-pressed={position === index}
          onClick={() => onPick(position)}
        >
          {formatLocation(location)}
        </button>
      ))}
    </div>
  );
}

/** Load one chunk and show its text (highlighted) or its page image. */
function ChunkView({ runId, location, quotes }: { runId: string; location: SourceLocation; quotes: string[] }) {
  const client = useApiClient();
  const [chunk, setChunk] = useState<ChunkSource | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Read the chunk once; answers after the view closed are ignored
  useEffect(() => {
    let isActive = true;
    getChunk(client, runId, location.chunk_id)
      .then((loaded) => isActive && setChunk(loaded))
      .catch((error: unknown) => isActive && setErrorMessage(describeError(error)));
    return () => {
      isActive = false;
    };
  }, [client, runId, location.chunk_id]);

  if (errorMessage !== null) return <ErrorMessage message={errorMessage} />;
  if (chunk === null) return <p className="muted">Loading the source…</p>;
  return (
    <div className="source-viewer__body">
      <div className="source-viewer__where">{formatLocation(chunk.location)}</div>
      {chunk.kind === "page_image" || chunk.text === null ? (
        <PageImage runId={runId} chunk={chunk} quotes={quotes} />
      ) : (
        <HighlightedText text={chunk.text} quotes={quotes} />
      )}
    </div>
  );
}

/** Show chunk text with each quote highlighted, and say which quotes were not found. */
export function HighlightedText({ text, quotes }: { text: string; quotes: string[] }) {
  const ranges: TextRange[] = [];
  const missing: string[] = [];
  // Each quote is found word for word (ignoring case and spacing), or listed as not found
  for (const quote of quotes) {
    const range = findQuoteRange(text, quote);
    if (range !== null) ranges.push(range);
    else missing.push(quote);
  }
  return (
    <>
      <div className="source-viewer__text" data-testid="source-text">
        {splitIntoSegments(text, ranges).map((segment, position) =>
          segment.isMarked ? <mark key={position}>{segment.text}</mark> : <span key={position}>{segment.text}</span>,
        )}
      </div>
      {missing.length > 0 && <QuoteList heading="Quoted text not found word for word in this passage:" quotes={missing} />}
    </>
  );
}

/** List quotes the viewer could not highlight. */
function QuoteList({ heading, quotes }: { heading: string; quotes: string[] }) {
  return (
    <div className="source-viewer__quotes">
      <div>{heading}</div>
      <ul>
        {quotes.map((quote) => (
          <li key={quote}>“{quote}”</li>
        ))}
      </ul>
    </div>
  );
}

/** Return a browser address for a Blob, or null where the browser cannot make one. */
function makeObjectUrl(blob: Blob): string | null {
  return typeof URL.createObjectURL === "function" ? URL.createObjectURL(blob) : null;
}

/** Load and show a scanned page; quotes are listed because an image cannot be highlighted. */
function PageImage({ runId, chunk, quotes }: { runId: string; chunk: ChunkSource; quotes: string[] }) {
  const client = useApiClient();
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Fetch the PNG through the API client and free its address when the view closes
  useEffect(() => {
    let isActive = true;
    let madeUrl: string | null = null;
    getChunkImage(client, runId, chunk.chunk_id)
      .then((blob) => {
        madeUrl = makeObjectUrl(blob);
        if (isActive) setImageUrl(madeUrl);
      })
      .catch((error: unknown) => isActive && setErrorMessage(describeError(error)));
    return () => {
      isActive = false;
      if (madeUrl !== null && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(madeUrl);
    };
  }, [client, runId, chunk.chunk_id]);

  const page = chunk.location.page;
  const altText = `Scanned page${page !== null && page !== undefined ? ` ${page}` : ""} of ${chunk.location.file_name ?? "the document"}`;
  return (
    <>
      <p className="muted">This is a scanned page, so the passage cannot be highlighted.</p>
      {errorMessage !== null && <ErrorMessage message={errorMessage} />}
      {imageUrl !== null && <img className="source-viewer__image" src={imageUrl} alt={altText} />}
      {quotes.length > 0 && <QuoteList heading="Look for:" quotes={quotes} />}
    </>
  );
}
