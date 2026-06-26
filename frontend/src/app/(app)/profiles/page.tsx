"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ProfileEditor } from "@/components/registry/ProfileEditor";
import { StatusBadge } from "@/components/registry/StatusBadge";
import { api, ApiError, type Profile, type Template } from "@/services/api";

export default function ProfilesPage() {
  const { me } = useAuth();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [editing, setEditing] = useState<Profile | null>(null);
  const [showEditor, setShowEditor] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.listProfiles().then(setProfiles).catch(() => setProfiles([]));
    api
      .listTemplates()
      .then((all) => setTemplates(all.filter((t) => t.status === "approved")))
      .catch(() => setTemplates([]));
  }, []);

  useEffect(() => load(), [load]);

  if (me && me.role !== "admin") {
    return <p className="text-sm text-ink/60">Profiles are managed by tenant admins.</p>;
  }

  const onSaved = () => {
    setShowEditor(false);
    setEditing(null);
    load();
  };

  const approve = async (id: string) => {
    try {
      await api.approveProfile(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Approve failed");
    }
  };

  return (
    <section aria-labelledby="profiles-heading" className="flex flex-col gap-8">
      <header className="flex items-start justify-between">
        <div>
          <h1 id="profiles-heading" className="text-2xl font-semibold text-ink">
            Stakeholder profiles
          </h1>
          <p className="mt-1 text-sm text-ink/60">
            Audience profiles that drive consistent, on-brand generation. Editing creates a new
            immutable version.
          </p>
        </div>
        {!showEditor && (
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setShowEditor(true);
            }}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            New profile
          </button>
        )}
      </header>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {showEditor && (
        <ProfileEditor
          templates={templates}
          editing={editing}
          onSaved={onSaved}
          onCancel={() => {
            setShowEditor(false);
            setEditing(null);
          }}
        />
      )}

      <div className="overflow-hidden rounded-2xl border border-ink/10 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-ink/[0.03] text-left text-xs uppercase tracking-wide text-ink/50">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Version</th>
              <th className="px-4 py-3">Audience</th>
              <th className="px-4 py-3">Tone</th>
              <th className="px-4 py-3">Slides</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {profiles.map((p) => (
              <tr key={`${p.id}-${p.version}`} className="border-t border-ink/5">
                <td className="px-4 py-3 font-medium text-ink">{p.name}</td>
                <td className="px-4 py-3 text-ink/60">v{p.version}</td>
                <td className="px-4 py-3 text-ink/60">{p.audience}</td>
                <td className="px-4 py-3 text-ink/60">{p.tone}</td>
                <td className="px-4 py-3 text-ink/60">
                  {p.slide_min}–{p.slide_max}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={p.status} />
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setEditing(p);
                        setShowEditor(true);
                      }}
                      className="rounded-lg border border-ink/15 px-3 py-1 text-xs hover:bg-ink/5"
                    >
                      Edit
                    </button>
                    {p.status === "draft" && (
                      <button
                        type="button"
                        onClick={() => approve(p.id)}
                        className="rounded-lg border border-ink/15 px-3 py-1 text-xs hover:bg-ink/5"
                      >
                        Approve
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {profiles.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-ink/50">
                  No profiles yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
