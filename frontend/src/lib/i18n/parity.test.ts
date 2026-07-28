/**
 * T-2.5: a missing translation must fail CI, not ship.
 *
 * Bahasa Indonesia is the default locale for the target users, so an English string
 * appearing mid-page is a visible defect. The message maps are plain objects, which
 * makes drift easy to introduce and invisible until someone reads that screen.
 */

import { describe, expect, it } from "vitest";

import { en } from "@/lib/i18n/messages/en";
import { id } from "@/lib/i18n/messages/id";

const enKeys = Object.keys(en).sort();
const idKeys = Object.keys(id).sort();

// `id` is typed Partial with an English fallback, so a gap degrades rather than
// crashes. It is still a visible defect for the target users -- Bahasa Indonesia is
// the default locale -- so parity is enforced as policy. It holds today at 168/168.
describe("locale parity", () => {
  it("has no key present in en but missing from id", () => {
    // Act
    const missing = enKeys.filter((k) => !(k in id));

    // Assert
    expect(missing).toEqual([]);
  });

  it("has no key present in id but missing from en", () => {
    // Act -- a stale key that no longer exists in the source locale
    const orphaned = idKeys.filter((k) => !(k in en));

    // Assert
    expect(orphaned).toEqual([]);
  });

  it("has no blank translations", () => {
    // Act
    const blank = Object.entries(id)
      .filter(([, value]) => typeof value === "string" && value.trim() === "")
      .map(([key]) => key);

    // Assert
    expect(blank).toEqual([]);
  });

  it("ships a non-empty catalogue", () => {
    // Guards against an import that silently resolves to {}, which would make
    // every assertion above vacuously true.
    expect(enKeys.length).toBeGreaterThan(50);
  });
});
