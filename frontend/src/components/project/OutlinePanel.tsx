"use client";

import { useEffect, useState } from "react";

import {
  api,
  ApiError,
  type Outline,
  type OutlineContent,
  type Profile,
} from "@/services/api";

interface Props {
  projectId: string;
  onOutlineReady: (outlineId: string | null) => void;
}

export function OutlinePanel({ projectId, onOutlineReady }: Props) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState("");
  const [outline, setOutline] = useState<Outline | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validatedAt, setValidatedAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .listProfiles()
      .then((all) => {
        const approved = all.filter((p) => p.status === "approved");
        setProfiles(approved);
        if (approved[0]) setProfileId(approved[0].id);
      })
      .catch(() => setProfiles([]));
  }, []);

  const build = async () => {
    if (!profileId) return;
    setError(null);
    setBusy(true);
    try {
      const built = await api.buildOutline(projectId, profileId);
      setOutline(built);
      onOutlineReady(built.valid ? built.id : null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Outline build failed");
    } finally {
      setBusy(false);
    }
  };

  const editPoint = (sectionId: string, index: number, text: string) => {
    if (!outline) return;
    let seen = -1;
    const next: OutlineContent = {
      ...outline.content,
      talking_points: outline.content.talking_points.map((tp) => {
        if (tp.section_id !== sectionId) return tp;
        seen += 1;
        return seen === index ? { ...tp, text } : tp;
      }),
    };
    setOutline({ ...outline, content: next });
  };

  const save = async () => {
    if (!outline) return;
    setError(null);
    setBusy(true);
    try {
      const saved = await api.updateOutline(outline.id, outline.content);
      setOutline(saved);
      setValidatedAt(Date.now());
      onOutlineReady(saved.valid ? saved.id : null);
    } catch (err) {
      // The backend re-validates on PUT; surface the validation message verbatim.
      setError(err instanceof ApiError ? err.message : "Save failed");
      onOutlineReady(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-ink">Outline</h2>
        <div className="flex items-center gap-2">
          <select
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            className="rounded-lg border border-ink/15 px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
          >
            {profiles.length === 0 && <option value="">No approved profiles</option>}
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} (v{p.version})
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={build}
            disabled={busy || !profileId}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Working…" : "Build outline"}
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
          ✕ {error}
        </p>
      )}

      {validatedAt && !error && outline?.valid && (
        <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          ✓ Outline re-validated — ready to regenerate (reuses existing analysis, no
          re-ingestion).
        </p>
      )}

      {outline && (
        <div className="flex flex-col gap-5">
          <p className="text-xs text-ink/50">
            schema {outline.schema_version} · {outline.valid ? "valid" : "invalid"} · structure is
            fixed by the profile; edit wording below.
          </p>
          {outline.content.sections.map((section) => {
            const points = outline.content.talking_points.filter(
              (tp) => tp.section_id === section.id,
            );
            return (
              <div key={section.id} className="border-l-2 border-accent/30 pl-4">
                <h3 className="font-medium text-ink">
                  {section.order + 1}. {section.title}
                </h3>
                <div className="mt-2 flex flex-col gap-1">
                  {points.map((tp, i) => (
                    <input
                      key={i}
                      value={tp.text}
                      onChange={(e) => editPoint(section.id, i, e.target.value)}
                      className="rounded-lg border border-ink/10 px-2 py-1 text-sm focus:border-accent focus:outline-none"
                    />
                  ))}
                  {points.length === 0 && (
                    <span className="text-xs text-ink/40">No talking points.</span>
                  )}
                </div>
              </div>
            );
          })}
          <button
            type="button"
            onClick={save}
            disabled={busy}
            className="self-start rounded-lg border border-ink/15 px-4 py-2 text-sm hover:bg-ink/5 disabled:opacity-50"
          >
            Save &amp; re-validate
          </button>
        </div>
      )}
    </div>
  );
}
