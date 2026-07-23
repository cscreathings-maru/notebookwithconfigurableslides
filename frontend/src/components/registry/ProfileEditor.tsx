"use client";

import { useState } from "react";

import {
  api,
  ApiError,
  type Profile,
  type ProfileInput,
  type Template,
  type Tone,
  type Verbosity,
} from "@/services/api";
import { SectionStructureBuilder } from "@/components/registry/SectionStructureBuilder";
import { useT } from "@/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/lib/i18n/messages/en";

const TONES: Tone[] = [
  "default",
  "casual",
  "professional",
  "funny",
  "educational",
  "sales_pitch",
];
const VERBOSITIES: Verbosity[] = ["concise", "standard", "text-heavy"];

interface Props {
  templates: Template[];
  editing: Profile | null;
  onSaved: () => void;
  onCancel: () => void;
}

function initialInput(editing: Profile | null, templates: Template[]): ProfileInput {
  if (editing) {
    return {
      name: editing.name,
      audience: editing.audience,
      template_id: editing.template_id,
      tone: editing.tone,
      verbosity: editing.verbosity,
      slide_min: editing.slide_min,
      slide_max: editing.slide_max,
      language: editing.language,
      section_structure: editing.section_structure as Array<{ title: string }>,
      prompt_config: editing.prompt_config,
    };
  }
  return {
    name: "",
    audience: "",
    template_id: templates[0]?.id ?? "",
    tone: "professional",
    verbosity: "standard",
    slide_min: 8,
    slide_max: 12,
    language: "Bahasa Indonesia",
    section_structure: [],
    prompt_config: {},
  };
}

export function ProfileEditor({ templates, editing, onSaved, onCancel }: Props) {
  const t = useT();
  const [form, setForm] = useState<ProfileInput>(() => initialInput(editing, templates));
  const [systemPrompt, setSystemPrompt] = useState<string>(
    typeof editing?.prompt_config?.system === "string"
      ? (editing.prompt_config.system as string)
      : "",
  );
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const set = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);
    const payload: ProfileInput = {
      ...form,
      prompt_config: systemPrompt ? { system: systemPrompt } : {},
    };
    try {
      if (editing) {
        await api.updateProfile(editing.id, payload);
      } else {
        await api.createProfile(payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t("profiles.saveFailed"));
    } finally {
      setSaving(false);
    }
  };

  const inputCls =
    "w-full rounded-lg border border-ink/15 px-3 py-2 text-sm focus:border-accent focus:outline-none";

  return (
    <form onSubmit={submit} className="flex flex-col gap-4 rounded-2xl border border-ink/10 bg-white p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-ink">
          {editing ? t("profiles.editVersion", { name: editing.name }) : t("profiles.new")}
        </h2>
        <button type="button" onClick={onCancel} className="text-sm text-ink/50 hover:text-ink">
          {t("common.cancel")}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("templates.name")}</span>
          <input
            required
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            className={inputCls}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("studio.template")}</span>
          <select
            value={form.template_id}
            onChange={(e) => set("template_id", e.target.value)}
            className={inputCls}
          >
            {templates.length === 0 && (
              <option value="">{t("profiles.noApprovedTemplates")}</option>
            )}
            {templates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name} (v{tpl.version})
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/60">{t("profiles.audience")}</span>
        <input
          required
          value={form.audience}
          onChange={(e) => set("audience", e.target.value)}
          placeholder={t("profiles.audiencePlaceholder")}
          className={inputCls}
        />
      </label>

      <div className="grid grid-cols-4 gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("studio.tone")}</span>
          <select value={form.tone} onChange={(e) => set("tone", e.target.value as Tone)} className={inputCls}>
            {TONES.map((x) => (
              <option key={x} value={x}>
                {t(`tone.${x}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("profiles.verbosity")}</span>
          <select
            value={form.verbosity}
            onChange={(e) => set("verbosity", e.target.value as Verbosity)}
            className={inputCls}
          >
            {VERBOSITIES.map((v) => (
              <option key={v} value={v}>
                {t(`density.${v}` as MessageKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("profiles.slidesMin")}</span>
          <input
            type="number"
            min={1}
            value={form.slide_min}
            onChange={(e) => set("slide_min", Number(e.target.value))}
            className={inputCls}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">{t("profiles.slidesMax")}</span>
          <input
            type="number"
            min={1}
            value={form.slide_max}
            onChange={(e) => set("slide_max", Number(e.target.value))}
            className={inputCls}
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/60">{t("studio.language")}</span>
        <input
          value={form.language}
          onChange={(e) => set("language", e.target.value)}
          className={`${inputCls} max-w-40`}
        />
      </label>

      <div className="flex flex-col gap-2 text-sm">
        <span className="text-ink/60">{t("profiles.sectionStructure")}</span>
        <SectionStructureBuilder
          value={form.section_structure as Array<{ title: string }>}
          onChange={(next) => set("section_structure", next)}
        />
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/60">{t("profiles.promptConfig")}</span>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={3}
          placeholder={t("profiles.promptPlaceholder")}
          className={inputCls}
        />
      </label>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={saving || form.template_id === ""}
        className="self-start rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {saving
          ? t("profiles.saving")
          : editing
            ? t("profiles.saveNewVersion")
            : t("profiles.createProfile")}
      </button>
    </form>
  );
}
