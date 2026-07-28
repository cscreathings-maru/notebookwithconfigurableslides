/**
 * T-2.5: section order pins the generated deck's structure, so reorder/delete are
 * correctness-critical and are pure state logic -- high value per test.
 *
 * The immutability assertions are deliberate: `move` swaps via a copy, and a
 * regression to in-place mutation would still "work" in the DOM while breaking
 * React's change detection in the parent form.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SectionStructureBuilder } from "@/components/registry/SectionStructureBuilder";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { id as messages } from "@/lib/i18n/messages/id";

// The app defaults to Bahasa Indonesia, so query by the label the user actually sees
// rather than hardcoding English -- that would break the moment a string is retranslated.
const LABEL = {
  up: messages["sections.moveUp"]!,
  down: messages["sections.moveDown"]!,
  remove: messages["sections.remove"]!,
  add: messages["sections.add"]!,
};

// Mirrors the component's Section shape: a title plus any extra per-section metadata
// a profile may carry.
type Section = { title: string; [key: string]: unknown };

const SECTIONS: Section[] = [{ title: "Summary" }, { title: "Results" }, { title: "Risks" }];

function renderBuilder(value: Section[] = SECTIONS) {
  const onChange = vi.fn();
  render(
    <LocaleProvider>
      <SectionStructureBuilder value={value} onChange={onChange} />
    </LocaleProvider>,
  );
  return onChange;
}

function rowButtons(label: string) {
  return screen.getAllByRole("button", { name: label });
}

describe("reordering", () => {
  it("swaps a section with the one above it", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act -- move "Results" up
    fireEvent.click(rowButtons(LABEL.up)[1]);

    // Assert
    expect(onChange).toHaveBeenCalledWith([
      { title: "Results" },
      { title: "Summary" },
      { title: "Risks" },
    ]);
  });

  it("swaps a section with the one below it", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act -- move "Summary" down
    fireEvent.click(rowButtons(LABEL.down)[0]);

    // Assert
    expect(onChange).toHaveBeenCalledWith([
      { title: "Results" },
      { title: "Summary" },
      { title: "Risks" },
    ]);
  });

  it("ignores moving the first section up", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act
    fireEvent.click(rowButtons(LABEL.up)[0]);

    // Assert -- no spurious change event, so the form stays pristine
    expect(onChange).not.toHaveBeenCalled();
  });

  it("ignores moving the last section down", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act
    fireEvent.click(rowButtons(LABEL.down)[SECTIONS.length - 1]);

    // Assert
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not mutate the array it was given", () => {
    // Arrange
    const original = [{ title: "Summary" }, { title: "Results" }];
    const snapshot = JSON.parse(JSON.stringify(original));
    const onChange = renderBuilder(original);

    // Act
    fireEvent.click(rowButtons(LABEL.down)[0]);

    // Assert
    expect(original).toEqual(snapshot);
    expect(onChange.mock.calls[0][0]).not.toBe(original);
  });
});

describe("adding and removing", () => {
  it("removes only the chosen section", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act -- drop "Results"
    fireEvent.click(rowButtons(LABEL.remove)[1]);

    // Assert
    expect(onChange).toHaveBeenCalledWith([{ title: "Summary" }, { title: "Risks" }]);
  });

  it("appends an empty section", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act
    fireEvent.click(screen.getByRole("button", { name: LABEL.add }));

    // Assert
    expect(onChange).toHaveBeenCalledWith([...SECTIONS, { title: "" }]);
  });
});

describe("editing", () => {
  it("updates one title without touching the others", () => {
    // Arrange
    const onChange = renderBuilder();

    // Act
    fireEvent.change(screen.getAllByRole("textbox")[2], {
      target: { value: "Strategic Risks" },
    });

    // Assert
    expect(onChange).toHaveBeenCalledWith([
      { title: "Summary" },
      { title: "Results" },
      { title: "Strategic Risks" },
    ]);
  });

  it("preserves fields other than the title", () => {
    // Arrange -- profiles may carry extra per-section metadata
    const onChange = renderBuilder([{ title: "Summary", weight: 3 }]);

    // Act
    fireEvent.change(screen.getAllByRole("textbox")[0], { target: { value: "Overview" } });

    // Assert
    expect(onChange).toHaveBeenCalledWith([{ title: "Overview", weight: 3 }]);
  });
});
