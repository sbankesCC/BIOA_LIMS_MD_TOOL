// The typed API client (openapi-fetch over the generated schema) and the React context
// that hands it to screens, so tests can pass a client with a mocked fetch.
import { createContext, useContext } from "react";
import createClient from "openapi-fetch";
import type { paths } from "./generated/schema";

export type ApiClient = ReturnType<typeof createClient<paths>>;

/** Options for a client: the API address and, in tests, a replacement fetch. */
export interface ApiClientOptions {
  baseUrl?: string;
  fetch?: (request: Request) => Promise<Response>;
}

// The Vite dev server proxies this prefix to the back end (see vite.config.ts)
export const API_BASE_URL = "/api";

/** Create an API client; the default calls the back end through the /api proxy. */
export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  return createClient<paths>({
    baseUrl: options.baseUrl ?? API_BASE_URL,
    fetch: options.fetch,
  });
}

// The app's client; tests wrap screens in a provider with their own client
export const ApiClientContext = createContext<ApiClient>(createApiClient());

/** Return the API client of the nearest provider (or the app's default client). */
export function useApiClient(): ApiClient {
  return useContext(ApiClientContext);
}
