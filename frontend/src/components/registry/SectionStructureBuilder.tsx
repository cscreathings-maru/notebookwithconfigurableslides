"use client";

/**
 * Ordered required-sections builder for a profile's structure contract.
 * Each entry is a section with a title; order is meaningful (it pins deck structure).
 */

interface Section {
  title: string;
  [key: string]: unknown;
}

interface Props {
  value: Section[];
  onChange: (next: Section[]) => void;
}

export function SectionStructureBuilder({ value, onChange }: Props) {
  const update = (index: number, title: string) =>
    onChange(value.map((s, i) => (i === index ? { ...s, title } : s)));

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div className="flex flex-col gap-2">
      {value.map((section, index) => (
        <div key={index} className="flex items-center gap-2">
          <span className="w-6 text-right text-xs text-ink/40">{index + 1}.</span>
          <input
            value={section.title}
            onChange={(e) => update(index, e.target.value)}
            placeholder="Section title"
            className="flex-1 rounded-lg border border-ink/15 px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            onClick={() => move(index, -1)}
            className="rounded px-2 py-1 text-xs text-ink/50 hover:bg-ink/5"
            aria-label="Move up"
          >
            ↑
          </button>
          <button
            type="button"
            onClick={() => move(index, 1)}
            className="rounded px-2 py-1 text-xs text-ink/50 hover:bg-ink/5"
            aria-label="Move down"
          >
            ↓
          </button>
          <button
            type="button"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
            className="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
            aria-label="Remove section"
          >
            ✕
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...value, { title: "" }])}
        className="self-start rounded-lg border border-dashed border-ink/20 px-3 py-1.5 text-xs text-ink/60 hover:bg-ink/5"
      >
        + Add section
      </button>
    </div>
  );
}
