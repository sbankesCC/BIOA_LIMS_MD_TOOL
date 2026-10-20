// Orders dropdown options by how close they are to a text, closest first (UI_SPEC §4.3).
// Used by the searchable dropdown: typed text filters and orders; a hint only orders.

/** Lower-case a text and keep only letters and digits, so "2–8 °C" and "2-8C" compare equal. */
export function normalizeForMatch(text: string): string {
  return text.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}]+/gu, "");
}

/** Return the set of two-character pieces of a normalized text (the text itself if shorter). */
function makeBigrams(text: string): string[] {
  if (text.length < 2) {
    return text.length === 0 ? [] : [text];
  }
  const bigrams: string[] = [];
  for (let index = 0; index < text.length - 1; index += 1) {
    bigrams.push(text.slice(index, index + 2));
  }
  return bigrams;
}

/** Return how alike two normalized texts are, from 0 (nothing shared) to 1 (same pieces). */
export function measureSimilarity(first: string, second: string): number {
  const firstBigrams = makeBigrams(first);
  const secondBigrams = makeBigrams(second);
  if (firstBigrams.length === 0 || secondBigrams.length === 0) {
    return 0;
  }
  // Dice coefficient: shared pieces, each piece of the second text used once
  const remaining = [...secondBigrams];
  let shared = 0;
  for (const bigram of firstBigrams) {
    const position = remaining.indexOf(bigram);
    if (position >= 0) {
      shared += 1;
      remaining.splice(position, 1);
    }
  }
  return (2 * shared) / (firstBigrams.length + secondBigrams.length);
}

// Match tiers, closest first: same text, starts with it, contains it (either way), only alike
const TIER_SAME = 0;
const TIER_STARTS_WITH = 1;
const TIER_CONTAINS = 2;
const TIER_ALIKE = 3;

// Options only alike (no containment) must be at least this similar to stay in a filtered list
export const MIN_FILTER_SIMILARITY = 0.4;

/** How one option compares with the text. */
interface RankedOption {
  option: string;
  index: number;
  tier: number;
  similarity: number;
}

/** Compare one option with a normalized text. */
function rankOption(option: string, index: number, target: string): RankedOption {
  const normalized = normalizeForMatch(option);
  const similarity = measureSimilarity(normalized, target);
  // Pick the closest tier the option reaches
  let tier = TIER_ALIKE;
  if (normalized === target) {
    tier = TIER_SAME;
  } else if (normalized.startsWith(target)) {
    tier = TIER_STARTS_WITH;
  } else if (normalized.includes(target) || (normalized.length > 0 && target.includes(normalized))) {
    tier = TIER_CONTAINS;
  }
  return { option, index, tier, similarity };
}

/** Sort ranked options: closest tier, then most similar, then their list order. */
function compareRanked(first: RankedOption, second: RankedOption): number {
  if (first.tier !== second.tier) return first.tier - second.tier;
  if (first.similarity !== second.similarity) return second.similarity - first.similarity;
  return first.index - second.index;
}

/**
 * Return the options closest to `text` first. With `isFilter`, options that neither contain
 * the text nor are alike enough are left out; without it every option stays (a hint).
 */
export function rankOptions(options: string[], text: string, isFilter: boolean): string[] {
  const target = normalizeForMatch(text);
  // No usable text: keep the list's own order
  if (target.length === 0) {
    return [...options];
  }
  const ranked = options.map((option, index) => rankOption(option, index, target));
  const kept = isFilter
    ? ranked.filter((item) => item.tier < TIER_ALIKE || item.similarity >= MIN_FILTER_SIMILARITY)
    : ranked;
  return kept.sort(compareRanked).map((item) => item.option);
}
