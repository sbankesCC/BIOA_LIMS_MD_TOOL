// Short names for the API shapes the screens use, all taken from the generated schema.
// Never write API types by hand: regenerate schema.ts with `npm run generate:api`.
import type { components } from "./generated/schema";

type Schemas = components["schemas"];

export type RunSummary = Schemas["RunSummary"];
export type RunDetail = Schemas["RunDetail"];
export type RunStatus = Schemas["RunSummary"]["status"];
export type RunIssue = Schemas["Issue"];
export type StartRunResponse = Schemas["StartRunResponse"];
export type ErrorResponse = Schemas["ErrorResponse"];

// Review screen shapes (M12)
export type ReviewView = Schemas["ReviewView"];
export type ReviewRow = Schemas["ReviewRow"];
export type ReviewCell = Schemas["ReviewCell"];
export type ReviewCounts = Schemas["ReviewCounts"];
export type IssueSummary = Schemas["IssueSummary"];
export type RunField = Schemas["RunField"];
export type RunFieldList = Schemas["RunFieldList"];
export type RecordDetail = Schemas["RecordDetail"];
export type ChunkSource = Schemas["ChunkSource"];
export type SourceLocation = Schemas["SourceLocation"];
export type CellSource = Schemas["CellSource"];
export type CellAlternative = Schemas["CellAlternative"];
export type ChangesRequest = Schemas["ChangesRequest"];
export type Change = ChangesRequest["changes"][number];
export type SetValueChange = Schemas["SetValueChange"];
export type PickAlternativeChange = Schemas["PickAlternativeChange"];
export type AcceptWarningChange = Schemas["AcceptWarningChange"];
export type SaveResult = Schemas["SaveResult"];
export type RecheckResult = Schemas["RecheckResult"];
