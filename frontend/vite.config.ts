// Vite and vitest settings for the front end.
// The dev server proxies /api to the back end, so the browser never needs CORS.
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Where the back end runs locally (uvicorn's default); API_PROXY_TARGET overrides it
const DEFAULT_API_TARGET = "http://127.0.0.1:8000";

// The front end calls the API under this prefix; the proxy removes it before forwarding
const API_PREFIX = "/api";

/** Build the proxy rule that forwards /api/... to the back end without the prefix. */
function makeApiProxy(target: string) {
  return {
    [API_PREFIX]: {
      target,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/api/, ""),
    },
  };
}

export default defineConfig(({ mode }) => {
  // Read API_PROXY_TARGET from the shell environment (all prefixes, so no VITE_ needed)
  const env = loadEnv(mode, ".", "");
  const apiProxy = makeApiProxy(env.API_PROXY_TARGET || DEFAULT_API_TARGET);
  return {
    plugins: [react()],
    server: { proxy: apiProxy },
    preview: { proxy: apiProxy },
    test: {
      environment: "jsdom",
      // Worker threads: forked workers time out while starting on the Windows dev machine
      pool: "threads",
      setupFiles: ["src/test/setup.ts"],
    },
  };
});
