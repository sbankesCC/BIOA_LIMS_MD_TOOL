// Helpers for the admin screens: which versions the history lists, the current version's entry,
// the "Changes" text of a version, the next version name and why an upload cannot be applied.
import type { DataVersionInfo, DataVersionList, LookupUploadReport, ReferenceUploadReport } from "../api/types";

/** The two kinds of admin data: lookup lists and reference data (existing Consumable Types). */
export type AdminKind = "lookup" | "reference";

/** A check report of either kind. */
export type UploadReport = LookupUploadReport | ReferenceUploadReport;

// Applied versions are named v1, v2, ... (PLAN.md "M7: version names")
const VERSION_PATTERN = /^v(\d+)$/;

/** Return the number of a `vN` version name, or null for another name (the seed, an upload ID). */
function readVersionNumber(versionId: string | null): number | null {
  const match = versionId === null ? null : VERSION_PATTERN.exec(versionId);
  return match !== null ? Number(match[1]) : null;
}

/** Return the versions that were applied at some point (they have a vN name), newest first. */
export function listAppliedVersions(list: DataVersionList): DataVersionInfo[] {
  const applied = list.versions.filter((version) => version.version_id !== null);
  return applied.sort((first, second) => (readVersionNumber(second.version_id) ?? 0) - (readVersionNumber(first.version_id) ?? 0));
}

/** Return the history entry of the current version, or null (e.g. the built-in seed lists). */
export function findCurrentVersion(list: DataVersionList): DataVersionInfo | null {
  return list.versions.find((version) => version.status === "current") ?? null;
}

/** Return the name the next applied upload gets: one more than the highest vN so far. */
export function findNextVersionName(list: DataVersionList): string {
  const numbers = list.versions.map((version) => readVersionNumber(version.version_id) ?? 0);
  return `v${Math.max(0, ...numbers) + 1}`;
}

/** Return a number stored in a version's summary, or null when it is not a number. */
function readSummaryNumber(version: DataVersionInfo, key: string): number | null {
  const value = version.summary[key];
  return typeof value === "number" ? value : null;
}

/** Return the "Changes" text of a version: "+4 values, −0" (lookup lists) or "120 types" (reference data). */
export function describeVersionChanges(version: DataVersionInfo, kind: AdminKind): string {
  if (kind === "lookup") {
    const added = readSummaryNumber(version, "added_values");
    const removed = readSummaryNumber(version, "removed_values");
    if (added === null || removed === null) return "—";
    return `+${added} ${added === 1 ? "value" : "values"}, −${removed}`;
  }
  const rows = readSummaryNumber(version, "row_count");
  return rows === null ? "—" : `${rows} existing ${rows === 1 ? "type" : "types"}`;
}

/** Return why the upload cannot be applied, or null when it can. */
export function describeApplyBlock(report: UploadReport, pending: DataVersionInfo | null): string | null {
  const count = report.problems.length;
  if (count > 0) {
    return `Fix the ${count} ${count === 1 ? "problem" : "problems"} and upload again to apply these updates`;
  }
  // A report without problems always comes with a pending version; say so plainly if it does not
  if (pending === null) {
    return "This upload was not kept. Upload the file again.";
  }
  return null;
}

/** Return true when the report is a lookup list report (it has a diff by sheet). */
export function isLookupReport(report: UploadReport): report is LookupUploadReport {
  return "changes" in report;
}

/** Format an API timestamp as a date, e.g. "16 Oct 2026". */
export function formatVersionDate(timestamp: string | null): string {
  if (timestamp === null) return "—";
  return new Date(timestamp).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
