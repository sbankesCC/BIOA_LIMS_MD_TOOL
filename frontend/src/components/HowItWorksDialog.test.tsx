// Tests for the "How it works" popup: opens on the first visit, remembered once closed,
// opens again from the top bar, and still works when localStorage is blocked.
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { ApiClientContext, createApiClient } from "../api/client";
import { makeFetchMock } from "../test/helpers";
import { HOW_IT_WORKS_SEEN_KEY } from "./HowItWorksDialog";

/** Render the app on the Start screen without marking the popup as seen. */
function renderFirstVisit() {
  const fetchMock = makeFetchMock(() => ({ status: 200, body: [] }));
  const client = createApiClient({ baseUrl: "http://localhost/api", fetch: fetchMock });
  return render(
    <ApiClientContext.Provider value={client}>
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    </ApiClientContext.Provider>,
  );
}

describe("How it works popup", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens by itself on the first visit", () => {
    renderFirstVisit();
    expect(screen.getByRole("dialog", { name: "How it works" })).not.toBeNull();
  });

  it("closing it is remembered, so the next visit does not open it", () => {
    const first = renderFirstVisit();
    fireEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(window.localStorage.getItem(HOW_IT_WORKS_SEEN_KEY)).toBe("yes");
    // A new visit (fresh render) finds the stored value and keeps the popup closed
    first.unmount();
    renderFirstVisit();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("the top bar button opens it again after it was seen", () => {
    window.localStorage.setItem(HOW_IT_WORKS_SEEN_KEY, "yes");
    renderFirstVisit();
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: /How it works/ })[0]);
    expect(screen.getByRole("dialog", { name: "How it works" })).not.toBeNull();
  });

  it("Escape closes it", () => {
    renderFirstVisit();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("blocked storage still shows the popup and closing does not crash", () => {
    // Storage that throws on every call, as in some private windows
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderFirstVisit();
    expect(screen.getByRole("dialog")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close how it works" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
