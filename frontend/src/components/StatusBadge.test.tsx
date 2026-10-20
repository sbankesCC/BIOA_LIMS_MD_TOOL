// Tests for the status badge: every status shows an icon and a word, never color alone.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunStatus } from "../api/types";
import { StatusBadge } from "./StatusBadge";

// Every run status in the API; the Record type makes the compiler flag a missing one
const EXPECTED_WORDS: Record<RunStatus, string> = {
  created: "Processing",
  ingesting: "Processing",
  extracting: "Processing",
  verifying_extraction: "Processing",
  transforming: "Processing",
  validating: "Processing",
  in_review: "Ready for review",
  rechecking: "Re-checking",
  failed: "Failed",
};

describe("StatusBadge", () => {
  it.each(Object.entries(EXPECTED_WORDS))("status %s shows an icon and the word %s", (status, word) => {
    const { container } = render(<StatusBadge status={status as RunStatus} />);
    // The word is visible text and the icon is an svg inside the same badge
    const badge = screen.getByText(word);
    expect(badge.querySelector("svg")).not.toBeNull();
    expect(container.textContent).toBe(word);
  });

  it("a verified run in review shows Verified with an icon", () => {
    render(<StatusBadge status="in_review" isVerified />);
    const badge = screen.getByText("Verified");
    expect(badge.querySelector("svg")).not.toBeNull();
  });

  it("a failed run never shows Verified", () => {
    render(<StatusBadge status="failed" isVerified />);
    expect(screen.queryByText("Verified")).toBeNull();
    expect(screen.getByText("Failed")).not.toBeNull();
  });
});
