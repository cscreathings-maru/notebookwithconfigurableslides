"use client";

import { useEffect, useState } from "react";

import { localeToLanguageName } from "@/lib/i18n/config";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import {
  api,
  ApiError,
  isSelectableTemplate,
  type ContentSource,
  type FreeformOutlineConfig,
  type Generation,
  type LanguageOption,
  type ModelOption,
  type Outline,
  type Template,
  type Tone,
  type Verbosity,
} from "@/services/api";

/**
 * DG-1/DG-2: outline-first deck building, triggered the same way GenerateCard was
 * (an explicit `/generate` or the ＋ button — never inferred from prose, same
 * reasoning as GenerateCard's docstring). Replaces GenerateCard as ChatPanel's
 * entry point: an outline is cheap and reversible, a deck is neither, so this
 * splits them into two deliberate confirmations instead of one.
 *
 * `Cancel` before a deck exists / `Discard` after -- costs nothing either way, the
 * outline row is simply abandoned (no delete endpoint exists or is needed for it).
 */
interface OutlineBuilderCardProps {
  projectId: string;
  /** Ground the outline in a specific assistant turn, when opened from one. */
  chatMessageId?: string;
  onCancel: () => void;
  onGenerated: (generation: Generation) => void;
}

const TONES: Tone[] = [
  "default",
  "professional",
  "casual",
  "educational",
  "funny",
  "sales_pitch",
];
const DENSITIES: Verbosity[] = ["concise", "standard", "text-heavy"];

type Phase = "setup" | "building" | "review" | "confirming";

export function OutlineBuilderCard({
  projectId,
  chatMessageId,
  onCancel,
  onGenerated,
}: OutlineBuilderCardProps) {
  const t = useT();
  const { locale } = useLocale();
  const [phase, setPhase] = useState<Phase>("setup");
  // Same auto-selection GenerateCard used: grounded in the turn it was opened
  // from, otherwise the notebook as a whole. Not exposed as a picker in v1 --
  // nothing in the locked decisions asked for one, and GenerateCard didn't have
  // one either.
  const contentSource: ContentSource = chatMessageId ? "chat" : "notebook";

  // Visible by default (Step 1 in the brief) -- distinct from the Advanced knobs
  // below, none of which the locked decisions (Q4) listed as hidden.
  const [templateId, setTemplateId] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]);

  const [tone, setTone] = useState<Tone>("professional");
  const [density, setDensity] = useState<Verbosity>("standard");
  const [nSlidesHint, setNSlidesHint] = useState("");
  const [language, setLanguage] = useState<string>(localeToLanguageName[locale]);
  const [model, setModel] = useState<string>("");
  const [webSearch, setWebSearch] = useState(false);
  const [exportAs, setExportAs] = useState<"pptx" | "pdf">("pptx");
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [outline, setOutline] = useState<Outline | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // DG-3.1: only templates the engine actually accepted change anything.
    api.listTemplates().then((all) => setTemplates(all.filter(isSelectableTemplate))).catch(() => {});
    api
      .listModels()
      .then((m) => {
        setModels(m);
        setModel(m.find((x) => x.default)?.id ?? m[0]?.id ?? "");
      })
      .catch(() => {});
    api
      .listLanguages()
      .then((langs) => {
        setLanguages(langs);
        const preferred = localeToLanguageName[locale];
        const match = langs.find((l) => l.id === preferred) ?? langs.find((l) => l.default);
        if (match) setLanguage(match.id);
      })
      .catch(() => {});
    // Only on mount -- re-running on locale change would clobber a user's
    // in-progress choice.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const outlineConfig = (): FreeformOutlineConfig => ({
    content_source: contentSource,
    chat_message_id: contentSource === "chat" ? chatMessageId : undefined,
    tone,
    density,
    n_slides_hint: nSlidesHint.trim() ? Number(nSlidesHint) : undefined,
    language: language || undefined,
  });

  const build = async () => {
    setError(null);
    setPhase("building");
    setBusy(true);
    try {
      const built = await api.buildFreeformOutline(projectId, outlineConfig());
      setOutline(built);
      setPhase("review");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("outline.buildFailed"));
      setPhase("setup");
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    setError(null);
    setBusy(true);
    try {
      // Same settings, a fresh draft -- no dedicated "rebuild" endpoint; this is
      // just calling build again, per the plan's build-order note (DG-1.3).
      const built = await api.buildFreeformOutline(projectId, outlineConfig());
      setOutline(built);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("outline.buildFailed"));
    } finally {
      setBusy(false);
    }
  };

  const editSectionTitle = (sectionId: string, title: string) => {
    if (!outline) return;
    setOutline({
      ...outline,
      content: {
        ...outline.content,
        sections: outline.content.sections.map((s) =>
          s.id === sectionId ? { ...s, title } : s,
        ),
      },
    });
  };

  const confirm = async () => {
    if (!outline) return;
    setError(null);
    setPhase("confirming");
    setBusy(true);
    try {
      // Persist any inline edits, THEN generate from the saved id -- the confirm
      // button is where "edited but not yet saved" has to stop being possible.
      const saved = await api.updateOutline(outline.id, outline.content);
      // Carries the SAME tone/density/language chosen for the outline through to
      // the render, plus the confirm-only knobs (template, model, web search,
      // export format) that outline building never needed.
      const generation = await api.createGeneration(projectId, saved.id, {
        tone,
        density,
        language: language || undefined,
        template_id: templateId || undefined,
        model: model || undefined,
        web_search: webSearch,
        export_as: exportAs,
      });
      onGenerated(generation);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("outline.generateFailed"));
      setPhase("review");
    } finally {
      setBusy(false);
    }
  };

  const backToSetup = () => {
    setPhase("setup");
    setError(null);
  };

  const advancedFields = (
    <div className="mb-3 grid grid-cols-3 gap-2">
      <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("studio.tone")}
        <select
          value={tone}
          onChange={(e) => setTone(e.target.value as Tone)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
        >
          {TONES.map((option) => (
            <option key={option} value={option}>
              {t(`tone.${option}` as MessageKey)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("studio.density")}
        <select
          value={density}
          onChange={(e) => setDensity(e.target.value as Verbosity)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
        >
          {DENSITIES.map((option) => (
            <option key={option} value={option}>
              {t(`density.${option}` as MessageKey)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("outline.slidesHint")}
        <input
          type="number"
          min={1}
          max={40}
          value={nSlidesHint}
          onChange={(e) => setNSlidesHint(e.target.value)}
          placeholder={t("outline.slidesHintPlaceholder")}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
        />
      </label>
      <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("studio.language")}
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
        >
          {languages.map((l) => (
            <option key={l.id} value={l.id}>
              {l.id}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("studio.model")}
        <select
          value={model}
          onChange={(e) => setModel(e.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
        >
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.id}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("studio.output")}
        <select
          value={exportAs}
          onChange={(e) => setExportAs(e.target.value as "pptx" | "pdf")}
          className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
        >
          <option value="pptx">PPTX</option>
          <option value="pdf">PDF</option>
        </select>
      </label>
      <label className="col-span-3 flex items-center gap-2 text-xs text-gray-700">
        <input
          type="checkbox"
          checked={webSearch}
          onChange={(e) => setWebSearch(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-accent focus:ring-accent"
        />
        <span className="font-medium">{t("studio.webSearch")}</span>
      </label>
    </div>
  );

  const templatePicker = (
    <div className="mb-3">
      <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-wide text-gray-500">
        {t("studio.template")}
      </span>
      <div className="flex gap-2 overflow-x-auto pb-1">
        <button
          type="button"
          onClick={() => setTemplateId("")}
          className={`shrink-0 rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
            templateId === ""
              ? "border-accent bg-accent/10 text-accent"
              : "border-gray-200 bg-white text-gray-600 hover:border-accent/50"
          }`}
        >
          {t("studio.defaultTheme")}
        </button>
        {templates.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            onClick={() => setTemplateId(tpl.id)}
            className={`flex shrink-0 flex-col items-center gap-1 rounded-lg border p-1.5 text-xs font-medium transition-colors ${
              templateId === tpl.id
                ? "border-accent bg-accent/10 text-accent"
                : "border-gray-200 bg-white text-gray-600 hover:border-accent/50"
            }`}
          >
            {tpl.thumbnail_urls[0] ? (
              // eslint-disable-next-line @next/next/no-img-element -- same-origin
              // engine-hosted preview, not an asset Next's optimizer needs to touch.
              <img
                src={tpl.thumbnail_urls[0]}
                alt=""
                className="h-12 w-20 rounded object-cover"
              />
            ) : (
              <span className="flex h-12 w-20 items-center justify-center rounded bg-gray-100 text-gray-400">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-5 w-5">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                </svg>
              </span>
            )}
            <span className="max-w-[80px] truncate">{tpl.name}</span>
          </button>
        ))}
      </div>
    </div>
  );

  if (phase === "setup" || phase === "building") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          build();
        }}
        aria-label={t("outline.setupTitle")}
        className="animate-fade-in rounded-xl border border-accent/25 bg-accent/5 p-4"
      >
        <div className="mb-3 flex items-center gap-2">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 text-accent">
            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
          </svg>
          <h3 className="text-sm font-semibold text-gray-900">{t("outline.setupTitle")}</h3>
        </div>

        <p className="mb-3 text-xs text-gray-600">
          {chatMessageId ? t("generate.fromMessage") : t("generate.fromNotebook")}
        </p>

        {templatePicker}

        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="mb-2 text-xs font-medium text-accent hover:underline"
        >
          {showAdvanced ? "▾" : "▸"} {t("outline.advanced")}
        </button>
        {showAdvanced && advancedFields}

        {error && (
          <div role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-xs text-red-600">
            {error}
          </div>
        )}

        <div className="flex items-center gap-2">
          <button type="submit" disabled={busy} className="btn-primary text-sm">
            {phase === "building" ? t("outline.building") : t("outline.buildOutline")}
          </button>
          <button type="button" onClick={onCancel} disabled={busy} className="btn-secondary text-sm">
            {t("common.cancel")}
          </button>
        </div>
      </form>
    );
  }

  // review | confirming -- the outline is guaranteed non-null in both.
  const sections = outline?.content.sections ?? [];
  const pointsFor = (sectionId: string) =>
    (outline?.content.talking_points ?? []).filter((tp) => tp.section_id === sectionId);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        confirm();
      }}
      aria-label={t("outline.reviewTitle")}
      className="animate-fade-in rounded-xl border border-accent/25 bg-accent/5 p-4"
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 text-accent">
            <line x1="8" y1="6" x2="21" y2="6" />
            <line x1="8" y1="12" x2="21" y2="12" />
            <line x1="8" y1="18" x2="21" y2="18" />
            <line x1="3" y1="6" x2="3.01" y2="6" />
            <line x1="3" y1="12" x2="3.01" y2="12" />
            <line x1="3" y1="18" x2="3.01" y2="18" />
          </svg>
          <h3 className="text-sm font-semibold text-gray-900">
            {t("outline.reviewTitle")} · {t("outline.sectionsCount", { n: sections.length })}
          </h3>
        </div>
        <button
          type="button"
          onClick={regenerate}
          disabled={busy}
          className="text-xs font-medium text-accent hover:underline disabled:opacity-50"
        >
          {busy && phase === "review" ? t("outline.regenerating") : `↻ ${t("outline.regenerate")}`}
        </button>
      </div>

      {sections.length === 0 && (
        <p className="mb-3 text-xs text-gray-500">{t("outline.noSections")}</p>
      )}

      <div className="mb-3 flex max-h-64 flex-col gap-3 overflow-y-auto pr-1">
        {sections.map((section) => (
          <div key={section.id} className="border-l-2 border-accent/30 pl-3">
            <input
              value={section.title}
              onChange={(e) => editSectionTitle(section.id, e.target.value)}
              disabled={busy}
              className="w-full rounded-md border border-transparent bg-transparent px-1 py-0.5 text-sm font-medium text-gray-900 hover:border-gray-200 focus:border-accent focus:bg-white focus:outline-none"
            />
            <ul className="mt-1 flex flex-col gap-0.5 pl-1">
              {pointsFor(section.id).map((tp, idx) => (
                <li key={idx} className="text-xs text-gray-500">
                  · {tp.text}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-xs text-red-600">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="submit"
          disabled={busy || sections.length === 0}
          className="btn-primary text-sm"
        >
          {phase === "confirming" ? t("outline.confirming") : t("outline.confirmGenerate")}
        </button>
        <button type="button" onClick={backToSetup} disabled={busy} className="btn-secondary text-sm">
          {t("outline.changeSettings")}
        </button>
        <button type="button" onClick={onCancel} disabled={busy} className="btn-secondary text-sm">
          {t("outline.discard")}
        </button>
        <span className="ml-auto text-[11px] text-gray-500">{t("generate.note")}</span>
      </div>
    </form>
  );
}
