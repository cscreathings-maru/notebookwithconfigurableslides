"use client";

import { useCallback, useEffect, useState } from "react";

import { SlideEditorModal } from "@/components/project/SlideEditorModal";
import { localeToLanguageName } from "@/lib/i18n/config";
import { useLocale, useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";
import {
  api,
  ApiError,
  type ContentSource,
  type DeckConfig,
  type Generation,
  type LanguageOption,
  type ModelOption,
  type Template,
  type Tone,
  type Verbosity,
} from "@/services/api";

const CONTENT_SOURCES: { value: ContentSource; labelKey: MessageKey }[] = [
  { value: "summary", labelKey: "studio.source.summary" },
  { value: "notebook", labelKey: "studio.source.notebook" },
  { value: "chat", labelKey: "studio.source.chat" },
  { value: "custom", labelKey: "studio.source.custom" },
];
const TONES: Tone[] = ["default", "casual", "professional", "funny", "educational", "sales_pitch"];
const DENSITIES: Verbosity[] = ["concise", "standard", "text-heavy"];

const STATUS_STYLE: Record<string, string> = {
  ready: "bg-emerald-500 text-emerald-700",
  failed: "bg-red-500 text-red-700",
  queued: "bg-gray-200 text-gray-500",
  generating: "bg-amber-500 text-amber-700",
  validating: "bg-amber-500 text-amber-700",
};

const TERMINAL = new Set(["ready", "failed"]);

export function StudioPanel({ projectId }: { projectId: string }) {
  const t = useT();
  const { locale } = useLocale();
  const [contentSource, setContentSource] = useState<ContentSource>("summary");
  const [customMarkdown, setCustomMarkdown] = useState("");
  const [tone, setTone] = useState<Tone>("professional");
  const [density, setDensity] = useState<Verbosity>("standard");
  const [nSlides, setNSlides] = useState(8);
  const [templateId, setTemplateId] = useState<string>("");
  const [webSearch, setWebSearch] = useState(false);
  const [model, setModel] = useState<string>("");
  const [language, setLanguage] = useState<string>(localeToLanguageName[locale]);
  const [exportAs, setExportAs] = useState<"pptx" | "pdf">("pptx");

  const [templates, setTemplates] = useState<Template[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [decks, setDecks] = useState<Generation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [activeEditorGenId, setActiveEditorGenId] = useState<string | null>(null);


  const loadDecks = useCallback(() => {
    api.listGenerations(projectId).then(setDecks).catch(() => setDecks([]));
  }, [projectId]);

  useEffect(() => {
    api.listTemplates().then((t) => setTemplates(t.filter((x) => x.status === "approved"))).catch(() => {});
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
    loadDecks();
  }, [loadDecks, locale]);

  const pollUntilDone = useCallback(
    async (id: string) => {
      for (let i = 0; i < 200; i++) {
        try {
          const g = await api.getGeneration(id);
          loadDecks();
          if (TERMINAL.has(g.status)) return;
        } catch {
          /* keep polling */
        }
        await new Promise((r) => setTimeout(r, 2500));
      }
    },
    [loadDecks],
  );

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const config: DeckConfig = {
        content_source: contentSource,
        tone,
        density,
        n_slides: nSlides,
        template_id: templateId || null,
        web_search: webSearch,
        model: model || undefined,
        export_as: exportAs,
        language: language || undefined,
      };
      if (contentSource === "custom") config.custom_markdown = customMarkdown;
      if (contentSource === "chat") {
        const thread = await api.listChat(projectId);
        const lastAnswer = [...thread].reverse().find((m) => m.role === "assistant");
        if (!lastAnswer) throw new ApiError(400, "no_chat", t("studio.askChatFirst"));
        config.chat_message_id = lastAnswer.id;
      }
      const gen = await api.generateDeck(projectId, config);
      loadDecks();
      pollUntilDone(gen.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("studio.startFailed"));
    } finally {
      setBusy(false);
    }
  };

  const download = async (g: Generation, fmt: "pptx" | "pdf") => {
    try {
      const { url } = await api.downloadGeneration(g.id, fmt);
      window.open(url, "_blank");
    } catch {
      setError(t("studio.downloadUnavailable"));
    }
  };

  return (
    <div className="card p-6 flex flex-col gap-6 h-full">
      <div className="flex items-center gap-2 border-b border-gray-100 pb-4">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5 text-accent">
          <path d="M12 2a10 10 0 0 0-10 10c0 5.523 4.477 10 10 10s10-4.477 10-10a10 10 0 0 0-10-10z" />
          <path d="M12 6v6l4 2" />
        </svg>
        <h2 className="text-base font-semibold text-gray-900">{t("studio.title")}</h2>
      </div>

      <div className="flex flex-col gap-5 overflow-y-auto flex-1 pr-2">
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-gray-700">{t("studio.contentSource")}</span>
          <select
            value={contentSource}
            onChange={(e) => setContentSource(e.target.value as ContentSource)}
            className="input-field"
          >
            {CONTENT_SOURCES.map((c) => (
              <option key={c.value} value={c.value}>
                {t(c.labelKey)}
              </option>
            ))}
          </select>
        </label>

        {contentSource === "custom" && (
          <textarea
            value={customMarkdown}
            onChange={(e) => setCustomMarkdown(e.target.value)}
            placeholder={t("studio.customPlaceholder")}
            rows={5}
            className="input-field font-mono text-xs"
          />
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("studio.template")}</span>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="input-field"
            >
              <option value="">{t("studio.defaultTheme")}</option>
              {templates.map((tpl) => (
                <option key={tpl.id} value={tpl.id}>
                  {tpl.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("studio.tone")}</span>
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value as Tone)}
              className="input-field"
            >
              {TONES.map((x) => (
                <option key={x} value={x}>
                  {t(`tone.${x}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("studio.density")}</span>
            <select
              value={density}
              onChange={(e) => setDensity(e.target.value as Verbosity)}
              className="input-field"
            >
              {DENSITIES.map((d) => (
                <option key={d} value={d}>
                  {t(`density.${d}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("studio.slides")}</span>
            <input
              type="number"
              min={1}
              max={40}
              value={nSlides}
              onChange={(e) => setNSlides(Number(e.target.value))}
              className="input-field"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("studio.output")}</span>
            <select
              value={exportAs}
              onChange={(e) => setExportAs(e.target.value as "pptx" | "pdf")}
              className="input-field"
            >
              <option value="pptx">PPTX</option>
              <option value="pdf">PDF</option>
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-gray-700">{t("studio.language")}</span>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="input-field"
            >
              {languages.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.id}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 sm:col-span-2">
            <span className="text-sm font-medium text-gray-700">{t("studio.model")}</span>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="input-field"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm text-gray-700 p-3 bg-gray-50 rounded-lg border border-gray-100 cursor-pointer hover:bg-gray-100 transition-colors">
          <input
            type="checkbox"
            checked={webSearch}
            onChange={(e) => setWebSearch(e.target.checked)}
            className="w-4 h-4 text-accent rounded border-gray-300 focus:ring-accent"
          />
          <span className="font-medium">{t("studio.webSearch")}</span>
        </label>
      </div>

      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="pt-4 border-t border-gray-100 flex flex-col gap-5">
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="btn-primary w-full py-2.5 flex items-center justify-center gap-2 text-base"
        >
          {busy ? (
            <svg className="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-5 h-5">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
          )}
          {busy ? t("studio.starting") : t("studio.generate")}
        </button>

        <div className="flex flex-col gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">{t("studio.decks")}</h3>
          {decks.length === 0 && (
            <div className="py-4 text-center rounded-lg border border-dashed border-gray-200">
              <p className="text-sm text-gray-400">{t("studio.noDecks")}</p>
            </div>
          )}
          
          <div className="flex flex-col gap-2 max-h-48 overflow-y-auto">
            {decks.map((g) => (
              <div
                key={g.id}
                className="flex items-center justify-between rounded-lg border border-gray-100 bg-white p-3 shadow-sm hover:shadow transition-shadow group"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${STATUS_STYLE[g.status]?.split(' ')[0] ?? "bg-gray-200"}`} />
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 capitalize">
                      {t(`status.gen.${g.status}` as MessageKey)}
                    </p>
                    <p className="text-xs text-gray-500 truncate mt-0.5">
                      {(g.params.tone as string) ?? "—"} · {(g.params.n_slides as number) ?? "—"} {t("studio.slidesUnit")}
                    </p>
                  </div>
                </div>
                
                {g.status === "ready" && (
                  <div className="flex shrink-0 gap-1.5 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={() => {
                        setActiveEditorGenId(g.id);
                        setEditorOpen(true);
                      }}
                      className="btn-secondary py-1 px-2 text-xs flex items-center gap-1 h-7 border-blue-300 text-blue-700 bg-blue-50 hover:bg-blue-100 dark:bg-blue-950 dark:text-blue-300"
                      title="Open interactive drag-and-edit slide canvas in Presenton"
                    >
                      <span>🎨 Editor</span>
                    </button>
                    {g.artifacts.pptx && (
                      <button
                        type="button"
                        onClick={() => download(g, "pptx")}
                        className="btn-secondary py-1 px-2 text-xs flex items-center gap-1 h-7"
                        title="Download PPTX"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        PPTX
                      </button>
                    )}
                    {g.artifacts.pdf && (
                      <button
                        type="button"
                        onClick={() => download(g, "pdf")}
                        className="btn-secondary py-1 px-2 text-xs flex items-center gap-1 h-7"
                        title="Download PDF"
                      >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-3.5 h-3.5">
                          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                          <polyline points="7 10 12 15 17 10" />
                          <line x1="12" y1="15" x2="12" y2="3" />
                        </svg>
                        PDF
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <SlideEditorModal
        isOpen={editorOpen}
        onClose={() => setEditorOpen(false)}
        title="🎨 Interactive Presentation Slide Editor"
        subtitle={`Polishing deck generation (${activeEditorGenId?.slice(0, 8)}...) — move components and adjust font styling`}
        editorUrl={`/presenton/presentation/${activeEditorGenId}`}
      />
    </div>
  );
}

