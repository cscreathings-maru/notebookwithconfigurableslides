"use client";

import { useCallback, useEffect, useState } from "react";

import { api, type Generation } from "@/services/api";
import { diffSections, type StructuralDiff } from "@/lib/structuralDiff";

const STATUS_STYLE: Record<string, string> = {
  ready: "text-emerald-600",
  failed: "text-red-600",
  queued: "text-ink/50",
  generating: "text-amber-600",
};

export function VersionHistoryPanel({
  projectId,
  refreshKey,
}: {
  projectId: string;
  refreshKey: number;
}) {
  const [rows, setRows] = useState<Generation[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [diff, setDiff] = useState<StructuralDiff | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listGenerations(projectId).then(setRows).catch(() => setRows([]));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const toggle = (id: string) => {
    setDiff(null);
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      return [...prev, id].slice(-2); // keep at most two
    });
  };

  const runDiff = async () => {
    setError(null);
    const [a, b] = selected
      .map((id) => rows.find((r) => r.id === id))
      .filter(Boolean) as Generation[];
    if (!a?.outline_id || !b?.outline_id) {
      setError("Both selected versions need an outline to diff.");
      return;
    }
    try {
      const [oa, ob] = await Promise.all([
        api.getOutline(a.outline_id),
        api.getOutline(b.outline_id),
      ]);
      setDiff(diffSections(oa.content.sections, ob.content.sections));
    } catch {
      setError("Could not load outlines to diff.");
    }
  };

  const preview = async (g: Generation) => {
    setError(null);
    try {
      const { url } = await api.downloadGeneration(g.id, g.artifacts.pdf ? "pdf" : "pptx");
      setPreviewUrl(url);
    } catch {
      setError("Preview unavailable.");
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">Version history</h2>
        <button
          type="button"
          onClick={runDiff}
          disabled={selected.length !== 2}
          className="rounded-lg border border-ink/15 px-3 py-1.5 text-xs hover:bg-ink/5 disabled:opacity-40"
        >
          Diff selected ({selected.length}/2)
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-left uppercase tracking-wide text-ink/50">
            <tr>
              <th className="py-2" />
              <th className="py-2">When</th>
              <th className="py-2">Status</th>
              <th className="py-2">Profile v</th>
              <th className="py-2">Template v</th>
              <th className="py-2">Model</th>
              <th className="py-2">Tone · slides</th>
              <th className="py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((g) => (
              <tr key={g.id} className="border-t border-ink/5">
                <td className="py-2">
                  <input
                    type="checkbox"
                    checked={selected.includes(g.id)}
                    onChange={() => toggle(g.id)}
                    aria-label="Select for diff"
                  />
                </td>
                <td className="py-2 text-ink/70">
                  {new Date(g.created_at).toLocaleString()}
                </td>
                <td className={`py-2 ${STATUS_STYLE[g.status] ?? "text-ink/60"}`}>{g.status}</td>
                <td className="py-2 text-ink/70">v{g.profile_version}</td>
                <td className="py-2 text-ink/70">v{g.template_version}</td>
                <td className="py-2 text-ink/70">{g.model ?? "—"}</td>
                <td className="py-2 text-ink/70">
                  {(g.params.tone as string) ?? "—"} · {(g.params.n_slides as number) ?? "—"}
                </td>
                <td className="py-2 text-right">
                  {g.status === "ready" && (
                    <button
                      type="button"
                      onClick={() => preview(g)}
                      className="rounded border border-ink/15 px-2 py-1 hover:bg-ink/5"
                    >
                      Preview
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="py-6 text-center text-ink/40">
                  No generations yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {diff && <DiffView diff={diff} />}

      {previewUrl && (
        <div className="mt-2">
          <p className="mb-1 text-xs text-ink/50">Deck preview</p>
          <iframe
            title="Deck preview"
            src={previewUrl}
            className="h-96 w-full rounded-lg border border-ink/10"
          />
        </div>
      )}
    </div>
  );
}

function DiffView({ diff }: { diff: StructuralDiff }) {
  if (diff.identical) {
    return <p className="text-sm text-emerald-600">Identical structure (section set and order).</p>;
  }
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-ink/[0.03] p-3 text-xs">
      {diff.reordered && <p className="text-amber-600">Sections reordered.</p>}
      {diff.added.length > 0 && (
        <p className="text-emerald-700">Added: {diff.added.join(", ")}</p>
      )}
      {diff.removed.length > 0 && (
        <p className="text-red-700">Removed: {diff.removed.join(", ")}</p>
      )}
      <ul className="mt-1 flex flex-col gap-0.5">
        {diff.order.map((o) => (
          <li key={o.title} className="text-ink/70">
            {o.title}:{" "}
            <span className="text-ink/50">
              {o.from === null ? "—" : `#${o.from + 1}`} → {o.to === null ? "—" : `#${o.to + 1}`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
