// Turns API failures into one error type with a plain-language message for the screens.
// The back end's messages already say what to do next; this adds messages for network failures.
import type { ErrorResponse } from "./types";

// Shown when the request never reached the back end (stopped server, wrong proxy target)
export const UNREACHABLE_MESSAGE =
  "The app could not reach its server. Check that the back end is running, then try again.";

/** An API call that failed: the API's error code, the HTTP status and a plain message. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly setting: string | null;

  constructor(code: string, status: number, message: string, setting: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.setting = setting;
  }
}

/** What an openapi-fetch call resolves to: data on success, error otherwise. */
interface ApiResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** Wait for an API call and return its data, or throw an ApiError with a plain message. */
export async function readApiResult<T>(call: Promise<ApiResult<T>>): Promise<T> {
  // A rejected fetch means the request never got an answer
  let result: ApiResult<T>;
  try {
    result = await call;
  } catch {
    throw new ApiError("NETWORK_ERROR", 0, UNREACHABLE_MESSAGE);
  }
  // Any error body or non-2xx status becomes an ApiError
  if (result.error !== undefined || !result.response.ok) {
    throw makeApiError(result.response.status, result.error);
  }
  return result.data as T;
}

/** Build an ApiError from a status and an error body that may or may not have the API's shape. */
export function makeApiError(status: number, body: unknown): ApiError {
  // The API's own error shape: use its code and message
  if (isErrorResponse(body)) {
    const { code, message, details } = body.error;
    const setting = typeof details?.setting === "string" ? details.setting : null;
    return new ApiError(code, status, message, setting);
  }
  // Anything else (the dev proxy's answer when the back end is stopped, an empty body)
  return new ApiError(
    "UNEXPECTED_RESPONSE",
    status,
    `The app did not get a usable answer from its server (status ${status}). Check that the back end is running, then try again.`,
  );
}

/** Return true when the body has the API's error shape. */
function isErrorResponse(body: unknown): body is ErrorResponse {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return false;
  }
  const error = (body as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { message?: unknown }).message === "string" &&
    typeof (error as { code?: unknown }).code === "string"
  );
}

/** Return the message to show for any thrown value, naming a missing setting when there is one. */
export function describeError(error: unknown): string {
  // Unknown errors get a generic plain message
  if (!(error instanceof ApiError)) {
    return "Something went wrong. Try again; if it keeps happening, check the back end.";
  }
  // A missing or wrong setting: make sure the setting's name is in the message
  if (error.setting !== null && !error.message.includes(error.setting)) {
    return `${error.message} (Setting: ${error.setting})`;
  }
  return error.message;
}
