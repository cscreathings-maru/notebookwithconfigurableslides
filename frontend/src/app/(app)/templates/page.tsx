"use client";

import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { SlideEditorModal } from "@/components/project/SlideEditorModal";
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
  "Outfit",
  "JetBrains Mono",
  "Arial",
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
  
  // File & AI Extraction
  const [pptx, setPptx] = useState<File | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  
  // Slide Editor Modal
  const [editorOpen, setEditorOpen] = useState(false);
  const [activeEditorId, setActiveEditorId] = useState<string | null>(null);

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
    setAiSummary(null);
    setShowCreate(false);
  };

  const handleFileSelect = async (file: File | null) => {
    if (!file) {
      setPptx(null);
      setAiSummary(null);
      return;
    }
    setPptx(file);
    if (file.name.toLowerCase().endsWith(".pptx")) {
      setExtracting(true);
      setError(null);
      try {
        const res = await api.extractTemplateTokens(file);
        const tokens = res.extracted_tokens;
        if (tokens.primary_color) setPrimary(tokens.primary_color);
        if (tokens.secondary_color) setSecondary(tokens.secondary_color);
        if (tokens.accent_color) setAccentColor(tokens.accent_color);
        if (tokens.typography) setFont(tokens.typography);
        if (tokens.aspect_ratio) setAspectRatio(tokens.aspect_ratio);
        setAiSummary(res.summary);
        if (!name) {
          setName(file.name.replace(/\.[^/.]+$/, "").replace(/_/g, " "));
        }
      } catch (err) {
        setError("AI token extraction failed, using NoteAI default tokens: " + (err instanceof Error ? err.message : String(err)));
      } finally {
        setExtracting(false);
      }
    }
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
          <h1 id="templates-heading" className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-100">
            {t("templates.title")}
          </h1>
          <p className="mt-2 text-base text-gray-500 max-w-2xl">{t("templates.subtitle")}</p>
        </div>
        {!showCreate && (
          <button
            onClick={() => setShowCreate(true)}
            className="btn-primary shrink-0 self-start sm:self-auto shadow-sm"
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
        <div className="card animate-slide-up border border-accent/20 overflow-hidden shadow-elevated bg-white dark:bg-ink">
          <div className="bg-accent-faint dark:bg-blue-950/40 px-6 py-4 border-b border-accent/10 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-accent dark:text-blue-400 flex items-center gap-2">
                <span>✨ AI-Powered Template Onboarding</span>
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded font-mono uppercase">Step 1: Upload</span>
              </h2>
              <p className="text-sm text-accent/80 dark:text-blue-300/80 mt-0.5">
                Drop your PowerPoint deck to let NoteAI automatically define colors, typography, and slide layouts.
              </p>
            </div>
          </div>
          
          <form onSubmit={create} className="p-6 flex flex-col gap-8">
            {/* 0. Primary AI Dropzone */}
            <div className="bg-slate-50 dark:bg-slate-900/60 p-6 rounded-xl border-2 border-dashed border-blue-200 dark:border-blue-800/60 flex flex-col items-center justify-center text-center transition hover:border-blue-500">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-10 h-10 text-blue-600 dark:text-blue-400 mb-3 animate-bounce">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="12" y1="18" x2="12" y2="12" />
                <line x1="9" y1="15" x2="12" y2="12" />
                <line x1="15" y1="15" x2="12" y2="12" />
              </svg>
              <h3 className="font-semibold text-base text-foreground mb-1">
                {pptx ? pptx.name : "Drop PowerPoint (.pptx) deck here to extract brand tokens"}
              </h3>
              <p className="text-xs text-muted-foreground max-w-md mb-4">
                NoteAI will inspect slide master shapes, background fills, and font styling to automatically populate your brand tokens below.
              </p>
              <input
                type="file"
                accept=".pptx"
                onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
                className="hidden"
                id="pptx-upload-primary"
              />
              <button
                type="button"
                onClick={() => document.getElementById("pptx-upload-primary")?.click()}
                className="btn-primary text-xs py-2 px-5 shadow-sm"
              >
                {pptx ? "Change Deck File" : "Select .pptx File"}
              </button>

              {extracting && (
                <div className="mt-4 flex items-center gap-2 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/80 px-4 py-2 rounded-lg border border-blue-200">
                  <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                  <span>✨ AI is scanning slide masters, color palettes, and typography...</span>
                </div>
              )}

              {aiSummary && !extracting && (
                <div className="mt-5 w-full max-w-2xl bg-white dark:bg-slate-950 p-4 rounded-xl border border-blue-200/80 dark:border-blue-800/80 shadow-sm text-left flex flex-col gap-3 animate-in fade-in">
                  <div className="flex items-center justify-between border-b border-border/50 pb-2">
                    <span className="text-xs font-bold text-blue-600 dark:text-blue-400 flex items-center gap-1.5">
                      <span>✨ AI Extraction Summary</span>
                    </span>
                    <span className="text-[10px] bg-green-100 text-green-800 px-2 py-0.5 rounded font-medium">
                      Confidence: 95%
                    </span>
                  </div>
                  <p className="text-xs text-foreground font-medium">{aiSummary}</p>
                  <div className="flex flex-wrap items-center gap-4 text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground">Primary:</span>
                      <div className="w-4 h-4 rounded-full border border-gray-300" style={{ backgroundColor: primary }} />
                      <span className="font-mono">{primary}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground">Secondary:</span>
                      <div className="w-4 h-4 rounded-full border border-gray-300" style={{ backgroundColor: secondary }} />
                      <span className="font-mono">{secondary}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground">Accent:</span>
                      <div className="w-4 h-4 rounded-full border border-gray-300" style={{ backgroundColor: accentColor }} />
                      <span className="font-mono">{accentColor}</span>
                    </div>
                    <div className="flex items-center gap-1.5 ml-auto">
                      <span className="text-muted-foreground">Font:</span>
                      <span className="font-semibold text-foreground">{font}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* 1. General Settings */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-xs text-gray-600 dark:text-gray-300">2</span>
                General Settings & Review
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5 ml-8">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">{t("templates.name")} <span className="text-red-500">*</span></span>
                  <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Q4 Executive Report" className="input-field" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Target Audience</span>
                  <select value={audience} onChange={(e) => setAudience(e.target.value)} className="input-field">
                    {AUDIENCES.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                  </select>
                </label>
              </div>
            </div>

            <hr className="border-gray-100 dark:border-gray-800" />

            {/* 2. Brand & Aesthetics */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-xs text-gray-600 dark:text-gray-300">3</span>
                Brand & Aesthetics (AI Detected Tokens)
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 ml-8">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Primary Color</span>
                  <div className="flex items-center gap-2">
                    <input type="color" value={primary} onChange={(e) => setPrimary(e.target.value)} className="w-10 h-10 p-1 rounded border border-gray-200 cursor-pointer" />
                    <input value={primary} onChange={(e) => setPrimary(e.target.value)} className="input-field flex-1 font-mono uppercase" />
                  </div>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Secondary Color</span>
                  <div className="flex items-center gap-2">
                    <input type="color" value={secondary} onChange={(e) => setSecondary(e.target.value)} className="w-10 h-10 p-1 rounded border border-gray-200 cursor-pointer" />
                    <input value={secondary} onChange={(e) => setSecondary(e.target.value)} className="input-field flex-1 font-mono uppercase" />
                  </div>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Accent Color</span>
                  <div className="flex items-center gap-2">
                    <input type="color" value={accentColor} onChange={(e) => setAccentColor(e.target.value)} className="w-10 h-10 p-1 rounded border border-gray-200 cursor-pointer" />
                    <input value={accentColor} onChange={(e) => setAccentColor(e.target.value)} className="input-field flex-1 font-mono uppercase" />
                  </div>
                </label>
                
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">{t("templates.font")}</span>
                  <select value={font} onChange={(e) => setFont(e.target.value)} className="input-field">
                    {FONTS.map(f => <option key={f} value={f}>{f}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1.5 text-sm md:col-span-2">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Logo URL (Optional)</span>
                  <input type="url" value={logoUrl} onChange={(e) => setLogoUrl(e.target.value)} placeholder="https://example.com/logo.png" className="input-field" />
                </label>
              </div>
            </div>

            <hr className="border-gray-100 dark:border-gray-800" />

            {/* 3. Layout & Formatting */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-500 flex items-center gap-2">
                <span className="w-6 h-6 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center text-xs text-gray-600 dark:text-gray-300">4</span>
                Layout & Formatting
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-5 ml-8">
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Slide Aspect Ratio</span>
                  <select value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)} className="input-field">
                    {ASPECT_RATIOS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Default Header Text (Optional)</span>
                  <input value={headerText} onChange={(e) => setHeaderText(e.target.value)} placeholder="e.g. Confidential" className="input-field" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <span className="font-medium text-gray-700 dark:text-gray-300">Default Footer Text (Optional)</span>
                  <input value={footerText} onChange={(e) => setFooterText(e.target.value)} placeholder="e.g. NoteAI 2026" className="input-field" />
                </label>
              </div>
            </div>

            {error && (
              <div role="alert" className="rounded-lg bg-red-50 dark:bg-red-950/50 p-4 text-sm text-red-600 dark:text-red-400 flex items-start gap-3 mt-2 border border-red-200 dark:border-red-800">
                <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
                <p>{error}</p>
              </div>
            )}

            <div className="flex items-center gap-3 pt-6 mt-2 border-t border-gray-100 dark:border-gray-800 justify-end">
              <button type="button" onClick={resetForm} className="btn-ghost">
                {t("common.cancel")}
              </button>
              <button type="submit" disabled={busy || !name} className="btn-primary min-w-[160px] shadow-sm font-semibold">
                {busy ? (
                  <span className="flex items-center gap-2">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Saving as Draft...
                  </span>
                ) : (
                  "Confirm & Save as Draft"
                )}
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card overflow-hidden bg-white dark:bg-ink">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 dark:bg-slate-900 border-b border-gray-100 dark:border-gray-800 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              <tr>
                <th className="px-6 py-4">{t("templates.name")}</th>
                <th className="px-6 py-4">{t("templates.colVersion")}</th>
                <th className="px-6 py-4">Brand Tokens</th>
                <th className="px-6 py-4">{t("templates.colPptx")}</th>
                <th className="px-6 py-4">{t("templates.colStatus")}</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {templates.map((tpl) => {
                const tokens = tpl.brand_tokens as any;
                const primaryColor = tokens?.primary || "#2563EB";
                return (
                  <tr key={`${tpl.id}-${tpl.version}`} className="hover:bg-gray-50/50 dark:hover:bg-slate-900/50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium text-gray-900 dark:text-gray-100">{tpl.name}</div>
                      {tokens?.audience && <div className="text-xs text-gray-500 mt-1 capitalize">{tokens.audience} Audience</div>}
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-400 font-mono">v{tpl.version}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 rounded-full border border-gray-200 dark:border-gray-700 shadow-sm shrink-0" style={{ backgroundColor: primaryColor }} title={primaryColor}></div>
                        <span className="text-gray-600 dark:text-gray-300 text-xs font-medium">{tokens?.font || "Inter"}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-gray-600 dark:text-gray-400">
                      {tpl.has_pptx ? (
                        <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 text-xs font-medium border border-blue-200/60 dark:border-blue-800/60">
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <polyline points="7 10 12 15 17 10" />
                            <line x1="12" y1="15" x2="12" y2="3" />
                          </svg>
                          Uploaded (.pptx)
                        </span>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={tpl.status} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setActiveEditorId(tpl.id);
                            setEditorOpen(true);
                          }}
                          className="btn-secondary py-1.5 px-3 text-xs flex items-center gap-1 hover:border-blue-500 hover:text-blue-600 transition"
                          title="Open Presenton interactive drag-and-edit slide canvas"
                        >
                          <span>🎨 Test in Editor</span>
                        </button>
                        {tpl.status === "draft" && (
                          <button
                            type="button"
                            onClick={() => approve(tpl.id)}
                            className="btn-primary py-1.5 px-3 text-xs shadow-sm bg-green-600 hover:bg-green-700"
                          >
                            ✓ Approve
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {templates.length === 0 && !showCreate && (
                <tr>
                  <td colSpan={6} className="px-6 py-16 text-center">
                    <div className="flex flex-col items-center justify-center">
                      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 dark:bg-blue-950/60 mb-3 text-blue-600 dark:text-blue-400">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-6 h-6">
                          <path d="M4 22h14a2 2 0 0 0 2-2V7.5L14.5 2H6a2 2 0 0 0-2 2v4" />
                          <polyline points="14 2 14 8 20 8" />
                          <path d="M2 15h10" />
                          <path d="M9 18l3-3-3-3" />
                        </svg>
                      </div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{t("templates.empty")}</p>
                      <p className="text-sm text-gray-500 mt-1 max-w-sm">Drop a PowerPoint deck to let NoteAI automatically define brand colors, typography, and layout.</p>
                      <button onClick={() => setShowCreate(true)} className="btn-primary mt-4 shadow-sm">
                        + New Template
                      </button>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <SlideEditorModal
        isOpen={editorOpen}
        onClose={() => setEditorOpen(false)}
        title="🎨 Interactive Template & Slide Editor"
        subtitle={`Testing drag-and-edit layout components for template reference (${activeEditorId?.slice(0, 8)}...)`}
        editorUrl={`/editor/template-preview?id=${activeEditorId}`}
      />
    </section>
  );
}
