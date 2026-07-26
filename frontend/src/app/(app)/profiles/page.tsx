"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ProfileEditor } from "@/components/registry/ProfileEditor";
import { StatusBadge } from "@/components/registry/StatusBadge";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Profile, type Template } from "@/services/api";

export default function ProfilesPage() {
  const { me } = useAuth();
  const t = useT();
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
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-12 h-12 text-gray-400 mb-4">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t("profiles.adminOnly")}</h2>
        <p className="text-gray-500 max-w-md">You do not have permission to access the Profile Manager. Please contact an administrator.</p>
      </div>
    );
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
      setError(err instanceof ApiError ? err.message : t("profiles.approveFailed"));
    }
  };

  return (
    <section aria-labelledby="profiles-heading" className="flex flex-col gap-8 animate-fade-in">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 id="profiles-heading" className="text-3xl font-bold tracking-tight text-gray-900">
            {t("profiles.title")}
          </h1>
          <p className="mt-2 text-base text-gray-500 max-w-2xl">{t("profiles.subtitle")}</p>
        </div>
        {!showEditor && (
          <button
            type="button"
            onClick={() => {
              setEditing(null);
              setShowEditor(true);
            }}
            className="btn-primary shrink-0 self-start sm:self-auto"
          >
            <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            {t("profiles.new")}
          </button>
        )}
      </header>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-600 flex items-start gap-3">
          <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <p>{error}</p>
        </div>
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

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
              <tr>
                <th className="px-6 py-4">{t("templates.name")}</th>
                <th className="px-6 py-4">{t("templates.colVersion")}</th>
                <th className="px-6 py-4">{t("profiles.colAudience")}</th>
                <th className="px-6 py-4">{t("studio.tone")}</th>
                <th className="px-6 py-4">{t("profiles.colSlides")}</th>
                <th className="px-6 py-4">{t("templates.colStatus")}</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {profiles.map((p) => (
                <tr key={`${p.id}-${p.version}`} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-6 py-4 font-medium text-gray-900">{p.name}</td>
                  <td className="px-6 py-4 text-gray-600">v{p.version}</td>
                  <td className="px-6 py-4 text-gray-600 capitalize">{p.audience}</td>
                  <td className="px-6 py-4 text-gray-600 capitalize">{p.tone}</td>
                  <td className="px-6 py-4 text-gray-600">
                    <span className="inline-flex items-center justify-center px-2 py-1 rounded bg-gray-100 text-xs font-medium text-gray-700">
                      {p.slide_min}–{p.slide_max}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <StatusBadge status={p.status} />
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setEditing(p);
                          setShowEditor(true);
                        }}
                        className="btn-ghost py-1.5 px-3 text-xs text-gray-600 hover:text-gray-900"
                      >
                        {t("common.edit")}
                      </button>
                      {p.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => approve(p.id)}
                          className="btn-secondary py-1.5 px-3 text-xs"
                        >
                          {t("common.approve")}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {profiles.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center justify-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-50 mb-3">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-gray-400">
                          <rect x="3" y="3" width="18" height="18" rx="2" />
                          <path d="M9 3v18" />
                        </svg>
                      </div>
                      <p className="text-sm font-medium text-gray-900">{t("profiles.empty")}</p>
                      <p className="text-sm text-gray-500 mt-1 max-w-sm">Create profiles to define specific content generation rules.</p>
                      <button 
                        onClick={() => {
                          setEditing(null);
                          setShowEditor(true);
                        }} 
                        className="btn-secondary mt-4"
                      >
                        Create Profile
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
