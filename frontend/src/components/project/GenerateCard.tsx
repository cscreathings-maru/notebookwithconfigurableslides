"use client";

import { useState } from "react";

import { useT } from "@/lib/i18n/LocaleProvider";
import { api, ApiError, type DeckConfig, type Generation, type Tone, type Verbosity } from "@/services/api";

/**
 * Phase D: generation triggered from chat, via an EXPLICIT confirmation card.
 *
 * Deliberately not free-text intent detection. Generation is billable, irreversible
 * and produces an artifact; letting a classifier fire it means "bisakah kamu ringkas
 * ini seperti presentasi?" can silently spend quota, while an explicit request that
 * the classifier misses looks broken. The card is opened by `/generate` (or the ＋
 * button), shows every parameter it will use, and only acts on a deliberate click.
 */
interface GenerateCardProps {
  projectId: string;
  /** Ground the deck in a specific assistant turn, when opened from one. */
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
const MIN_SLIDES = 3;
const MAX_SLIDES = 30;

export function GenerateCard({
  projectId,
  chatMessageId,
  onCancel,
  onGenerated,
}: GenerateCardProps) {
  const t = useT();
  const [tone, setTone] = useState<Tone>("professional");
  const [density, setDensity] = useState<Verbosity>("standard");
  const [slides, setSlides] = useState(8);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const config: DeckConfig = {
      // A card opened from a turn is grounded in that turn; otherwise the notebook.
      content_source: chatMessageId ? "chat" : "notebook",
      chat_message_id: chatMessageId,
      tone,
      density,
      n_slides: slides,
      web_search: false,
      export_as: "pptx",
    };
    try {
      onGenerated(await api.generateDeck(projectId, config));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("generate.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      aria-label={t("generate.title")}
      className="animate-fade-in rounded-xl border border-accent/25 bg-accent/5 p-4"
    >
      <div className="mb-3 flex items-center gap-2">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 text-accent">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
        <h3 className="text-sm font-semibold text-gray-900">{t("generate.title")}</h3>
      </div>

      <p className="mb-3 text-xs text-gray-600">
        {chatMessageId ? t("generate.fromMessage") : t("generate.fromNotebook")}
      </p>

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
                {option}
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
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] font-medium uppercase tracking-wide text-gray-500">
          {t("studio.slides")}
          <input
            type="number"
            min={MIN_SLIDES}
            max={MAX_SLIDES}
            value={slides}
            onChange={(e) => setSlides(Number(e.target.value))}
            className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-sm text-gray-800 focus:border-accent focus:outline-none"
          />
        </label>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-lg bg-red-50 p-2 text-xs text-red-600">
          {error}
        </div>
      )}

      <div className="flex items-center gap-2">
        <button type="submit" disabled={busy} className="btn-primary text-sm">
          {busy ? t("generate.working") : t("generate.confirm")}
        </button>
        <button type="button" onClick={onCancel} className="btn-secondary text-sm">
          {t("common.cancel")}
        </button>
        <span className="ml-auto text-[11px] text-gray-500">{t("generate.note")}</span>
      </div>
    </form>
  );
}
