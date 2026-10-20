// Reads the existing LabVantage types an issue names (`details.candidates` of POSSIBLE_DUPLICATE
// and EXISTS_IN_LABVANTAGE) and says in plain words why each one matched.
// The match words are the tool's contract (CONTRACTS §3a and the duplicate check), not client data.

/** One existing type from the issue details, as the API gives it. */
export interface DuplicateCandidate {
  candidateId: string | null;
  name: string;
  match: string | null;
  reason: string | null;
}

// Plain explanations of each way a name can match an existing type
const MATCH_TEXTS: Record<string, string> = {
  exact: "Exactly the same name",
  normalized: "Same name apart from capitals, spaces or °",
  same: "The duplicate checker thinks it is the same type",
  unsure: "The duplicate checker could not tell",
};

/** Return a text field of an object, or null when it is missing or not text. */
function readText(item: Record<string, unknown>, key: string): string | null {
  const value = item[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Return the existing types listed in an issue's details; entries without a name are left out. */
export function readDuplicateCandidates(details: Record<string, unknown> | undefined): DuplicateCandidate[] {
  const list = details?.candidates;
  if (!Array.isArray(list)) return [];
  const candidates: DuplicateCandidate[] = [];
  for (const entry of list) {
    if (typeof entry !== "object" || entry === null) continue;
    const item = entry as Record<string, unknown>;
    const name = readText(item, "name");
    if (name === null) continue;
    candidates.push({ candidateId: readText(item, "candidate_id"), name, match: readText(item, "match"), reason: readText(item, "reason") });
  }
  return candidates;
}

/** Return the plain explanation of how a candidate matched ("—" when the API gives none). */
export function describeMatch(match: string | null): string {
  if (match === null) return "—";
  return MATCH_TEXTS[match] ?? match;
}
