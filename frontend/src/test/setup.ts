// Test setup run before every test file: unmount rendered screens and clear stored values.
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Each test starts with an empty page and empty localStorage
afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
