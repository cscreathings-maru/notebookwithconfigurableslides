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
  const [showCreate, setShowCreate] = useState(false);

  const canCreate = me?.role === "admin" || me?.role === "author";

  const load = useCallback(() => {
    api.listProjects().then(setProjects).catch(() => setProjects([]));
  }, []);

  useEffect(() => load(), [load]);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setError(null);
    setBusy(true);
    try {
      await api.createProject(name);
      setName("");
      setShowCreate(false);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("projects.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="projects-heading" className="flex flex-col gap-8 animate-fade-in">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 id="projects-heading" className="text-3xl font-bold tracking-tight text-gray-900">
            {t("projects.title")}
          </h1>
          <p className="mt-2 text-base text-gray-500 max-w-2xl">{t("projects.subtitle")}</p>
        </div>
        {canCreate && !showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary shrink-0 self-start sm:self-auto"
          >
            <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Project
          </button>
        )}
      </header>

      {showCreate && (
        <form
          onSubmit={create}
          className="card p-6 flex flex-col sm:flex-row sm:items-end gap-4 animate-slide-up"
        >
          <label className="flex flex-1 flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("projects.newName")}</span>
            <input
              required
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Q3 Marketing Review"
              className="input-field"
            />
          </label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                setShowCreate(false);
                setName("");
              }}
              className="btn-ghost"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={busy || !name.trim()}
              className="btn-primary min-w-[100px]"
            >
              {busy ? "..." : t("common.create")}
            </button>
          </div>
        </form>
      )}

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-600 flex items-start gap-3">
          <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <p>{error}</p>
        </div>
      )}

      <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {projects.map((p, i) => (
          <li key={p.id} className="animate-fade-in" style={{ animationDelay: `${i * 50}ms`, animationFillMode: 'both' }}>
            <Link
              href={`/projects/${p.id}`}
              className="card block p-6 h-full border-t-4 border-t-transparent hover:border-t-accent transition-all group"
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-faint text-accent mb-4 group-hover:bg-accent group-hover:text-white transition-colors">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-gray-900 group-hover:text-accent transition-colors line-clamp-1">{p.name}</h2>
              <p className="mt-2 text-sm text-gray-500 flex items-center gap-1.5">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4 opacity-70">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                {new Date(p.created_at).toLocaleDateString(locale === "id" ? "id-ID" : "en-US", { 
                  month: 'short', day: 'numeric', year: 'numeric' 
                })}
              </p>
            </Link>
          </li>
        ))}
        
        {projects.length === 0 && !showCreate && (
          <li className="col-span-full">
            <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-gray-200 bg-gray-50 py-16 px-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white shadow-sm mb-4">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-gray-400">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h3 className="text-sm font-semibold text-gray-900 mb-1">{t("projects.empty")}</h3>
              <p className="text-sm text-gray-500 mb-4 max-w-sm">Get started by creating a new project to upload sources and generate presentations.</p>
              {canCreate && (
                <button onClick={() => setShowCreate(true)} className="btn-secondary">
                  Create Project
                </button>
              )}
            </div>
          </li>
        )}
      </ul>
    </section>
  );
}
