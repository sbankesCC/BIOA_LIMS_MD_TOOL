// Finds quoted passages in a source chunk's text so the source viewer can highlight them.
// Matching ignores case and treats runs of spaces and table bars ("|") as one space,
// like the back end's citation check.

/** A highlighted stretch of the text: start (inclusive) and end (exclusive) positions. */
export interface TextRange {
  start: number;
  end: number;
}

/** A piece of the text to show, marked or not. */
export interface TextSegment {
  text: string;
  isMarked: boolean;
}

/** Return true for characters that count as a gap between words. */
function isGap(character: string): boolean {
  return /\s/.test(character) || character === "|";
}

/** Collapse gaps to one space and lower-case; `positions` maps each kept character back. */
function squeezeText(text: string): { squeezed: string; positions: number[] } {
  let squeezed = "";
  const positions: number[] = [];
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    // A gap becomes one space, and only after a non-gap character
    if (isGap(character)) {
      if (squeezed.length > 0 && !squeezed.endsWith(" ")) {
        squeezed += " ";
        positions.push(index);
      }
      continue;
    }
    // Lower-casing can give more than one character; each maps back to the same position
    const lower = character.toLowerCase();
    squeezed += lower;
    for (let count = 0; count < lower.length; count += 1) {
      positions.push(index);
    }
  }
  return { squeezed, positions };
}

/** Return where the quote is in the text, or null when it is not there word for word. */
export function findQuoteRange(text: string, quote: string): TextRange | null {
  const source = squeezeText(text);
  const target = squeezeText(quote).squeezed.trim();
  if (target.length === 0) {
    return null;
  }
  const found = source.squeezed.indexOf(target);
  if (found < 0) {
    return null;
  }
  // Map the first and last matched characters back to the original text
  const start = source.positions[found];
  const end = source.positions[found + target.length - 1] + 1;
  return { start, end };
}

/** Merge overlapping ranges, in text order. */
function mergeRanges(ranges: TextRange[]): TextRange[] {
  const sorted = [...ranges].sort((first, second) => first.start - second.start);
  const merged: TextRange[] = [];
  for (const range of sorted) {
    const last = merged[merged.length - 1];
    if (last !== undefined && range.start <= last.end) {
      last.end = Math.max(last.end, range.end);
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}

/** Split the text into marked and unmarked pieces for the given ranges. */
export function splitIntoSegments(text: string, ranges: TextRange[]): TextSegment[] {
  const segments: TextSegment[] = [];
  let position = 0;
  // Each range adds the plain text before it, then its marked text
  for (const range of mergeRanges(ranges)) {
    if (range.start > position) {
      segments.push({ text: text.slice(position, range.start), isMarked: false });
    }
    segments.push({ text: text.slice(range.start, range.end), isMarked: true });
    position = range.end;
  }
  if (position < text.length) {
    segments.push({ text: text.slice(position), isMarked: false });
  }
  return segments;
}
