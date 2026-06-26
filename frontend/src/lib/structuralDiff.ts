/**
 * Structural diff between two outlines' section sets/order.
 *
 * Structure is the consistency contract, so this compares section titles and their
 * order — not wording. Used to show what changed between two generations.
 */

import type { OutlineSection } from "@/services/api";

export interface StructuralDiff {
  identical: boolean;
  reordered: boolean;
  added: string[];
  removed: string[];
  order: Array<{ title: string; from: number | null; to: number | null }>;
}

export function diffSections(
  a: OutlineSection[],
  b: OutlineSection[],
): StructuralDiff {
  const aTitles = [...a].sort((x, y) => x.order - y.order).map((s) => s.title);
  const bTitles = [...b].sort((x, y) => x.order - y.order).map((s) => s.title);

  const aSet = new Set(aTitles);
  const bSet = new Set(bTitles);

  const added = bTitles.filter((t) => !aSet.has(t));
  const removed = aTitles.filter((t) => !bSet.has(t));

  const order = [...new Set([...aTitles, ...bTitles])].map((title) => {
    const from = aTitles.indexOf(title);
    const to = bTitles.indexOf(title);
    return { title, from: from < 0 ? null : from, to: to < 0 ? null : to };
  });

  const sameSet = added.length === 0 && removed.length === 0;
  const reordered =
    sameSet && aTitles.some((t, i) => t !== bTitles[i]);
  const identical = sameSet && !reordered;

  return { identical, reordered, added, removed, order };
}
