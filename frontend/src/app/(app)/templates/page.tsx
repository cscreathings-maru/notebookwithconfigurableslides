"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { StatusBadge } from "@/components/registry/StatusBadge";
import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type Template } from "@/services/api";

const FONTS = [
  "Inter",
  "Roboto",
  "Playfair Display",
  "Montserrat",
  "Open Sans",
  "Lato",
];

const AUDIENCES = [
  { value: "internal", label: "Internal Team" },
  { value: "client", label: "Client Facing" },
  { value: "public", label: "Public Release" },
];

const ASPECT_RATIOS = [
  { value: "16:9", label: "Widescreen (16:9)" },
  { value: "4:3", label: "Standard (4:3)" },
];

export default function TemplatesPage() {
  const { me } = useAuth();
  const t = useT();
  const [templates, setTemplates] = useState<Template[]>([]);
  
  // Form State
  const [name, setName] = useState("");
  const [audience, setAudience] = useState("internal");
  
  // Brand Tokens
  const [primary, setPrimary] = useState("#2563EB");
  const [secondary, setSecondary] = useState("#1E40AF");
  const [accentColor, setAccentColor] = useState("#F59E0B");
  const [font, setFont] = useState("Inter");
  const [logoUrl, setLogoUrl] = useState("");
  
  // Layout & Formatting
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [headerText, setHeaderText] = useState("");
  const [footerText, setFooterText] = useState("");
  
  // File
  const [pptx, setPptx] = useState<File | null>(null);
  
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(() => {
    api.listTemplates().then(setTemplates).catch(() => setTemplates([]));
  }, []);

  useEffect(() => load(), [load]);

  if (me && me.role !== "admin") {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-12 h-12 text-gray-400 mb-4">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t("templates.adminOnly")}</h2>
        <p className="text-gray-500 max-w-md">You do not have permission to access the Template Builder. Please contact an administrator.</p>
      </div>
    );
  }

  const resetForm = () => {
    setName("");
    setAudience("internal");
    setPrimary("#2563EB");
    setSecondary("#1E40AF");
    setAccentColor("#F59E0B");
    setFont("Inter");
    setLogoUrl("");
    setAspectRatio("16:9");
    setHeaderText("");
    setFooterText("");
    setPptx(null);
    setShowCreate(false);
  };

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.createTemplate({
        name,
        brand_tokens: { 
          primary, 
          secondary,
          accent: accentColor,
          font,
          audience,
          logoUrl,
          aspectRatio,
          headerText,
          footerText
        },
        pptx,
      });
      resetForm();
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("templates.createFailed"));
    } finally {
      setBusy(false);
    }
  };

  const approve = async (id: string) => {
    try {
      await api.approveTemplate(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("templates.approveFailed"));
    }
  };

  return (
    <section aria-labelledby="templates-heading" className="flex flex-col gap-8 animate-fade-in">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 id="templates-heading" className="text-3xl font-bold tracking-tight text-gray-900">
            {t("templates.title")}
          </h1>
          <p className="mt-2 text-base text-gray-500 max-w-2xl">{t("templates.subtitle")}</p>
        </div>
        {!showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary shrink-0 self-start sm:self-auto"
          >
            <svg className="mr-2 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Template
          </button>
        )}
      </header>

      {showCreate && (
        <div className="card animate-slide-up border border-accent/20 overflow-hidden shadow-elevated">
          <div className="bg-accent-faint px-6 py-4 border-b border-accent/10">
            <h2 className="text-lg font-semibold text-accent">Template Builder Configurator</h2>
            <p className="text-sm text-accent/80 mt-1">Configure Presenton generation properties for this template.</p>
          </div>
          
          <form onSubmit={create} className="p-6 flex flex-col gap-8 bg-white">
            {/* 1. General Settings */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs text-gray-600">1</span>
                General Settings
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5 ml-8">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">{t("templates.name")} <span className="text-red-500">*</span></span>
                  <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Q4 Executive Report" className="input-field" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Target Audience</span>
                  <select value={audience} onChange={(e) => setAudience(e.target.value)} className="input-field">
                    {AUDIENCES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                  </select>
                </label>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* 2. Brand & Aesthetics */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs text-gray-600">2</span>
                Brand & Aesthetics
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 ml-8">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Primary Color</span>
                  <div className="flex items-center gap-2">
                    <input type="color" value={primary} onChange={(e) => setPrimary(e.target.value)} className="w-10 h-10 p-1 rounded border border-gray-200 cursor-pointer" />
                    <input value={primary} onChange={(e) => setPrimary(e.target.value)} className="input-field flex-1 font-mono uppercase" />
                  </div>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Secondary Color</span>
                  <div className="flex items-center gap-2">
                    <input type="color" value={secondary} onChange={(e) => setSecondary(e.target.value)} className="w-10 h-10 p-1 rounded border border-gray-200 cursor-pointer" />
                    <input value={secondary} onChange={(e) => setSecondary(e.target.value)} className="input-field flex-1 font-mono uppercase" />
                  </div>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Accent Color</span>
                  <div className="flex items-center gap-2">
                    <input type="color" value={accentColor} onChange={(e) => setAccentColor(e.target.value)} className="w-10 h-10 p-1 rounded border border-gray-200 cursor-pointer" />
                    <input value={accentColor} onChange={(e) => setAccentColor(e.target.value)} className="input-field flex-1 font-mono uppercase" />
                  </div>
                </label>
                
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">{t("templates.font")}</span>
                  <select value={font} onChange={(e) => setFont(e.target.value)} className="input-field">
                    {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1.5 text-sm md:col-span-2">
                  <span className="font-medium text-gray-700">Logo URL (Optional)</span>
                  <input type="url" value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://example.com/logo.png" className="input-field" />
                </label>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* 3. Layout & Formatting */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs text-gray-600">3</span>
                Layout & Formatting
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 ml-8">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Slide Aspect Ratio</span>
                  <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="input-field">
                    {ASPECT_RATIOS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Default Header Text (Optional)</span>
                  <input value={headerText} onChange={(e) => setHeaderText(e.target.value)} placeholder="e.g. Confidential" className="input-field" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700">Default Footer Text (Optional)</span>
                  <input value={footerText} onChange={(e) => setFooterText(e.target.value)} placeholder="e.g. NoteAI 2026" className="input-field" />
                </label>
              </div>
            </div>

            <hr className="border-gray-100" />

            {/* 4. Base Template Upload */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center text-xs text-gray-600">4</span>
                Base Template Upload
              </h3>
              <div className="ml-8">
                <label className="flex flex-col gap-1.5 text-sm max-w-md">
                  <span className="font-medium text-gray-700">{t("templates.importPptx")}</span>
                  <div className="border-2 border-dashed border-gray-200 rounded-lg p-6 flex flex-col items-center justify-center bg-gray-50 hover:bg-gray-100 hover:border-accent transition-colors">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-8 h-8 text-gray-400 mb-2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <polyline points="10 9 9 9 8 9" />
                    </svg>
                    <span className="text-sm font-medium text-gray-600 mb-1">{pptx ? pptx.name : "Click to select a PPTX file"}</span>
                    <span className="text-xs text-gray-400">Master slides from this file will be preserved</span>
                    <input
                      type="file"
                      accept=".pptx"
                      onChange={(e) => setPptx(e.target.files?.[0] ?? null)}
                      className="hidden"
                      id="pptx-upload"
                    />
                    <button type="button" onClick={() => document.getElementById('pptx-upload')?.click()} className="mt-4 btn-secondary text-xs">Browse Files</button>
                  </div>
                </label>
              </div>
            </div>

            {error && (
              <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-600 flex items-start gap-3 mt-2">
                <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <p>{error}</p>
              </div>
            )}

            <div className="flex items-center gap-3 pt-6 mt-2 border-t border-gray-100 justify-end">
              <button type="button" onClick={resetForm} className="btn-ghost">
                {t("common.cancel")}
              </button>
              <button type="submit" disabled={busy || !name} className="btn-primary min-w-[140px]">
                {busy ? (
                  <span className="flex items-center gap-2">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    {t("templates.creating")}
                  </span>
                ) : (
                  t("templates.create")
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">
              <tr>
                <th className="px-6 py-4">{t("templates.name")}</th>
                <th className="px-6 py-4">{t("templates.colVersion")}</th>
                <th className="px-6 py-4">Brand Tokens</th>
                <th className="px-6 py-4">{t("templates.colPptx")}</th>
                <th className="px-6 py-4">{t("templates.colStatus")}</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {templates.map((tpl) => {
                const tokens = tpl.brand_tokens as any;
                const primaryColor = tokens?.primary || "#E5E7EB";
                return (
                  <tr key={`${tpl.id}-${tpl.version}`} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900">{tpl.name}</div>
                      {tokens?.audience && <div className="text-xs text-gray-500 mt-1 capitalize">{tokens.audience} Audience</div>}
                    </td>
                    <td className="px-6 py-4 text-gray-600">v{tpl.version}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full border border-gray-200 shadow-sm" style={{ backgroundColor: primaryColor }} title={primaryColor}></div>
                        <span className="text-gray-600 text-xs">{tokens?.font || "Inter"}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-gray-600">
                      {tpl.has_pptx ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-accent/5 text-accent text-xs font-medium border border-accent/10">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <polyline points="7 10 12 15 17 10" />
                            <line x1="12" y1="15" x2="12" y2="3" />
                          </svg>
                          Uploaded
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={tpl.status} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      {tpl.status === "draft" && (
                        <button
                          type="button"
                          onClick={() => approve(tpl.id)}
                          className="btn-secondary py-1.5 px-3 text-xs"
                        >
                          {t("common.approve")}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {templates.length === 0 && !showCreate && (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center justify-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-50 mb-3">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6 text-gray-400">
                          <path d="M4 22h14a2 2 0 0 0 2-2V7.5L14.5 2H6a2 2 0 0 0-2 2v4" />
                          <polyline points="14 2 14 8 20 8" />
                          <path d="M2 15h10" />
                          <path d="M9 18l3-3-3-3" />
                        </svg>
                      </div>
                      <p className="text-sm font-medium text-gray-900">{t("templates.empty")}</p>
                      <p className="text-sm text-gray-500 mt-1 max-w-sm">Create templates with brand tokens to automatically style presentations during generation.</p>
                      <button onClick={() => setShowCreate(true)} className="btn-secondary mt-4">
                        Create Template
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
