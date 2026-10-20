// A React hook that reads the details of a record's issues (GET /runs/{id}/records/{record_id})
// or of the run's issues (from the run), for the panel's extra lines: the checker's note,
// matching existing types, other records with the same name.
import { useEffect, useState } from "react";
import { useApiClient } from "../api/client";
import { describeError } from "../api/errors";
import { getRecord } from "../api/review";
import type { RunDetail, RunIssue } from "../api/types";

/** The full issues of the panel's record (or run), and an error when they could not be read. */
export interface IssueDetailsState {
  issues: RunIssue[];
  errorMessage: string | null;
}

/** Load the full issues of a record, or take the run's issues when `recordId` is null. */
export function useIssueDetails(run: RunDetail, recordId: string | null, reloadKey: unknown): IssueDetailsState {
  const client = useApiClient();
  const [loaded, setLoaded] = useState<IssueDetailsState>({ issues: [], errorMessage: null });

  // Read the record whenever it changes or the view is reloaded (a new `reloadKey`)
  useEffect(() => {
    if (recordId === null) return;
    let isActive = true;
    getRecord(client, run.run_id, recordId)
      .then((detail) => isActive && setLoaded({ issues: detail.issues, errorMessage: null }))
      .catch((error: unknown) => isActive && setLoaded({ issues: [], errorMessage: describeError(error) }));
    return () => {
      isActive = false;
    };
  }, [client, run.run_id, recordId, reloadKey]);

  return recordId === null ? { issues: run.run_issues, errorMessage: null } : loaded;
}

/** Return the plain lines that explain an issue's details; `nameOf` turns record IDs into names. */
export function describeIssueDetails(issue: RunIssue | undefined, nameOf: (recordId: string) => string): string[] {
  if (issue === undefined) return [];
  const details = issue.details as Record<string, unknown>;
  const lines: string[] = [];
  // The verification agent's note on the record
  if (typeof details.note === "string" && details.note.length > 0) {
    lines.push(`Checker's note: ${details.note}`);
  }
  // Existing Consumable Types with a matching or similar name
  if (Array.isArray(details.candidates)) {
    const names = details.candidates.map(readCandidateName).filter((name): name is string => name !== null);
    if (names.length > 0) lines.push(`Existing types: ${names.join("; ")}`);
  }
  // Other records of this run with the same name
  if (Array.isArray(details.records)) {
    const others = details.records.filter((id): id is string => typeof id === "string").map(nameOf);
    if (others.length > 0) lines.push(`Same name as: ${others.join("; ")}`);
  }
  return lines;
}

/** Return the name of a matching existing type from the issue details, or null. */
function readCandidateName(candidate: unknown): string | null {
  if (typeof candidate !== "object" || candidate === null) return null;
  const name = (candidate as { name?: unknown }).name;
  return typeof name === "string" ? name : null;
}
