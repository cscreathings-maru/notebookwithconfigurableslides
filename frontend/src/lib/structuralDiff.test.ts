/**
 * T-2.5: structure is the consistency contract between generations, so the diff that
 * reports it is worth pinning. Pure logic, no DOM, high value per test.
 */

import { describe, expect, it } from "vitest";

import { diffSections } from "@/lib/structuralDiff";

const section = (title: string, order: number) => ({ id: title, title, order });

describe("diffSections", () => {
  it("reports identical section sets in the same order", () => {
    // Arrange
    const a = [section("Summary", 0), section("Results", 1)];

    // Act
    const diff = diffSections(a, [...a]);

    // Assert
    expect(diff).toMatchObject({
      identical: true,
      reordered: false,
      added: [],
      removed: [],
    });
  });

  it("compares by order, not array position", () => {
    // Arrange -- same structure, shuffled input arrays
    const a = [section("Results", 1), section("Summary", 0)];
    const b = [section("Summary", 0), section("Results", 1)];

    // Act
    const diff = diffSections(a, b);

    // Assert
    expect(diff.identical).toBe(true);
  });

  it("detects a reorder of an unchanged set", () => {
    // Arrange
    const a = [section("Summary", 0), section("Results", 1)];
    const b = [section("Results", 0), section("Summary", 1)];

    // Act
    const diff = diffSections(a, b);

    // Assert
    expect(diff.reordered).toBe(true);
    expect(diff.identical).toBe(false);
    expect([diff.added, diff.removed]).toEqual([[], []]);
  });

  it("reports additions", () => {
    // Arrange
    const a = [section("Summary", 0)];
    const b = [section("Summary", 0), section("Risks", 1)];

    // Act
    const diff = diffSections(a, b);

    // Assert
    expect(diff.added).toEqual(["Risks"]);
    expect(diff.removed).toEqual([]);
    expect(diff.identical).toBe(false);
  });

  it("reports removals", () => {
    // Arrange
    const a = [section("Summary", 0), section("Risks", 1)];
    const b = [section("Summary", 0)];

    // Act
    const diff = diffSections(a, b);

    // Assert
    expect(diff.removed).toEqual(["Risks"]);
    expect(diff.added).toEqual([]);
  });

  it("never reports a reorder when the set itself changed", () => {
    // Arrange -- a swap plus an addition is an add, not a reorder
    const a = [section("Summary", 0), section("Results", 1)];
    const b = [section("Results", 0), section("Summary", 1), section("Risks", 2)];

    // Act
    const diff = diffSections(a, b);

    // Assert
    expect(diff.reordered).toBe(false);
    expect(diff.added).toEqual(["Risks"]);
  });

  it("maps each title to its position on both sides", () => {
    // Arrange
    const a = [section("Summary", 0), section("Gone", 1)];
    const b = [section("Summary", 0), section("New", 1)];

    // Act
    const { order } = diffSections(a, b);

    // Assert -- null marks absence on that side
    expect(order).toEqual([
      { title: "Summary", from: 0, to: 0 },
      { title: "Gone", from: 1, to: null },
      { title: "New", from: null, to: 1 },
    ]);
  });

  it("treats two empty outlines as identical", () => {
    // Act
    const diff = diffSections([], []);

    // Assert
    expect(diff).toMatchObject({ identical: true, reordered: false, order: [] });
  });
});
