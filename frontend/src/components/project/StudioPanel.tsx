"use client";

import { useCallback, useEffect, useState } from "react";

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
  ready: "text-emerald-600",
  failed: "text-red-600",
  queued: "text-ink/50",
  generating: "text-amber-600",
  validating: "text-amber-600",
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
        // Prefer the language matching the current UI locale; else the API default.
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
    <div className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <h2 className="text-lg font-semibold text-ink">{t("studio.title")}</h2>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/60">{t("studio.contentSource")}</span>
        <select
          value={contentSource}
          onChange={(e) => setContentSource(e.target.value as ContentSource)}
          className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
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
          className="rounded-lg border border-ink/15 px-3 py-2 font-mono text-xs focus:border-accent focus:outline-none"
        />
      )}

      <div className="grid grid-cols-2 gap-3 text-sm">
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.tone")}</span>
          <select
            value={tone}
            onChange={(e) => setTone(e.target.value as Tone)}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          >
            {TONES.map((x) => (
              <option key={x} value={x}>
                {t(`tone.${x}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.density")}</span>
          <select
            value={density}
            onChange={(e) => setDensity(e.target.value as Verbosity)}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          >
            {DENSITIES.map((d) => (
              <option key={d} value={d}>
                {t(`density.${d}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.slides")}</span>
          <input
            type="number"
            min={1}
            max={40}
            value={nSlides}
            onChange={(e) => setNSlides(Number(e.target.value))}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.output")}</span>
          <select
            value={exportAs}
            onChange={(e) => setExportAs(e.target.value as "pptx" | "pdf")}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          >
            <option value="pptx">PPTX</option>
            <option value="pdf">PDF</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.language")}</span>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          >
            {languages.map((l) => (
              <option key={l.id} value={l.id}>
                {l.id}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.template")}</span>
          <select
            value={templateId}
            onChange={(e) => setTemplateId(e.target.value)}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          >
            <option value="">{t("studio.defaultTheme")}</option>
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-ink/60">{t("studio.model")}</span>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-lg border border-ink/15 px-3 py-2 focus:border-accent focus:outline-none"
          >
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm text-ink/70">
        <input
          type="checkbox"
          checked={webSearch}
          onChange={(e) => setWebSearch(e.target.checked)}
        />
        {t("studio.webSearch")}
      </label>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={generate}
        disabled={busy}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {busy ? t("studio.starting") : t("studio.generate")}
      </button>

      <div className="mt-2 flex flex-col gap-2">
        <p className="text-xs uppercase tracking-wide text-ink/50">{t("studio.decks")}</p>
        {decks.length === 0 && <p className="text-sm text-ink/40">{t("studio.noDecks")}</p>}
        {decks.map((g) => (
          <div
            key={g.id}
            className="flex items-center justify-between rounded-lg border border-ink/10 px-3 py-2 text-sm"
          >
            <div className="min-w-0">
              <span className={STATUS_STYLE[g.status] ?? "text-ink/60"}>
                {t(`status.gen.${g.status}` as MessageKey)}
              </span>
              <span className="ml-2 text-ink/50">
                {(g.params.tone as string) ?? "—"} · {(g.params.n_slides as number) ?? "—"}{" "}
                {t("studio.slidesUnit")}
              </span>
            </div>
            {g.status === "ready" && (
              <div className="flex shrink-0 gap-2">
                {g.artifacts.pptx && (
                  <button
                    type="button"
                    onClick={() => download(g, "pptx")}
                    className="rounded border border-ink/15 px-2 py-1 text-xs hover:bg-ink/5"
                  >
                    PPTX
                  </button>
                )}
                {g.artifacts.pdf && (
                  <button
                    type="button"
                    onClick={() => download(g, "pdf")}
                    className="rounded border border-ink/15 px-2 py-1 text-xs hover:bg-ink/5"
                  >
                    PDF
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
