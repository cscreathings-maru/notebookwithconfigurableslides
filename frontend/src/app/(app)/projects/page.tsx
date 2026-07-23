"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Project } from "@/services/api";

export default function ProjectsPage() {
  const { me } = useAuth();
  const { locale } = useLocale();
  const t = useT();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const canCreate = me?.role === "admin" || me?.role === "author";

  const load = useCallback(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  useEffect(() => load(), [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createProject(name);
      setName("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("projects.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="projects-heading" className="flex flex-col gap-8">
      <header>
        <h1 id="projects-heading" className="text-2xl font-semibold text-ink">
          {t("projects.title")}
        </h1>
        <p className="mt-1 text-sm text-ink/60">{t("projects.subtitle")}</p>
      </header>

      {canCreate && (
        <form
          onSubmit={create}
          className="flex items-end gap-3 rounded-2xl border border-ink/10 bg-white p-5"
        >
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span className="text-ink/60">{t("projects.newName")}</span>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-lg border border-ink/15 px-3 py-2 text-sm focus:border-accent focus:outline-none"
            />
          </label>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            {t("common.create")}
          </button>
        </form>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <ul className="grid grid-cols-2 gap-4">
        {projects.map((p) => (
          <li key={p.id}>
            <Link
              href={`/projects/${p.id}`}
              className="block rounded-2xl border border-ink/10 bg-white p-5 transition-colors hover:border-accent/40"
            >
              <p className="font-semibold text-ink">{p.name}</p>
              <p className="mt-1 text-xs text-ink/50">
                {new Date(p.created_at).toLocaleDateString(locale === "id" ? "id-ID" : "en-US")}
              </p>
            </Link>
          </li>
        ))}
        {projects.length === 0 && (
          <li className="col-span-2 rounded-2xl border border-dashed border-ink/15 p-10 text-center text-sm text-ink/50">
            {t("projects.empty")}
          </li>
        )}
      </ul>
    </section>
  );
}
