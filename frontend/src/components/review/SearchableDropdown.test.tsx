// Tests for the searchable dropdown: closest options first, filtering while typing, keyboard
// picking and the combobox roles screen readers use. Options are synthetic.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SearchableDropdown } from "./SearchableDropdown";

// Synthetic list values
const OPTIONS = ["Room shelf", "Fridge 2-8", "Freezer minus 20", "Fridge door"];

/** Render the dropdown with a spy for picked values. */
function renderDropdown(hint: string | null = null) {
  const onChange = vi.fn();
  render(<SearchableDropdown label="Storage" options={OPTIONS} value="" hint={hint} onChange={onChange} />);
  return { onChange, box: screen.getByRole("combobox", { name: "Storage" }) };
}

/** Return the option texts in the order shown. */
function readOptions(): string[] {
  return screen.getAllByRole("option").map((option) => option.textContent ?? "");
}

describe("SearchableDropdown", () => {
  it("before typing, orders every option by the hint, closest first", () => {
    const { box } = renderDropdown("freezer -20");
    fireEvent.focus(box);
    expect(readOptions()[0]).toBe("Freezer minus 20");
    expect(readOptions()).toHaveLength(4);
  });

  it("typing filters the options and puts the closest first", () => {
    const { box } = renderDropdown();
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "fridge d" } });
    expect(readOptions()).toEqual(["Fridge door", "Fridge 2-8"]);
  });

  it("says when nothing matches", () => {
    const { box } = renderDropdown();
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: "xyz" } });
    expect(screen.getByText("No list value matches. Try other words.")).not.toBeNull();
  });

  it("arrow keys move the highlight and Enter picks it", () => {
    const { box, onChange } = renderDropdown();
    fireEvent.change(box, { target: { value: "fridge" } });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(box.getAttribute("aria-activedescendant")).toContain("option-1");
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("Fridge door");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("Escape closes the list", () => {
    const { box } = renderDropdown();
    fireEvent.focus(box);
    expect(box.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(box, { key: "Escape" });
    expect(box.getAttribute("aria-expanded")).toBe("false");
  });
});
