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
