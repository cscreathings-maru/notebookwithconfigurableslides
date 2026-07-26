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

  return (
    <div className="card animate-slide-up border border-accent/20 overflow-hidden shadow-elevated">
      <div className="bg-accent-faint px-6 py-4 border-b border-accent/10 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-accent">
            {editing ? t("profiles.editVersion", { name: editing.name }) : t("profiles.new")}
          </h2>
          <p className="text-sm text-accent/80 mt-0.5">Configure target audience and presentation structure.</p>
        </div>
      </div>

      <form onSubmit={submit} className="p-6 flex flex-col gap-6 bg-white">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-gray-700">{t("templates.name")}</span>
            <input
              required
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              className="input-field"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-gray-700">{t("studio.template")}</span>
            <select
              value={form.template_id}
              onChange={(e) => set("template_id", e.target.value)}
              className="input-field"
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

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-gray-700">{t("profiles.audience")}</span>
          <input
            required
            value={form.audience}
            onChange={(e) => set("audience", e.target.value)}
            placeholder={t("profiles.audiencePlaceholder")}
            className="input-field"
          />
        </label>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-gray-700">{t("studio.tone")}</span>
            <select value={form.tone} onChange={(e) => set("tone", e.target.value as Tone)} className="input-field">
              {TONES.map((x) => (
                <option key={x} value={x}>
                  {t(`tone.${x}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-gray-700">{t("profiles.verbosity")}</span>
            <select
              value={form.verbosity}
              onChange={(e) => set("verbosity", e.target.value as Verbosity)}
              className="input-field"
            >
              {VERBOSITIES.map((v) => (
                <option key={v} value={v}>
                  {t(`density.${v}` as MessageKey)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-gray-700">{t("profiles.slidesMin")}</span>
            <input
              type="number"
              min={1}
              value={form.slide_min}
              onChange={(e) => set("slide_min", Number(e.target.value))}
              className="input-field"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-gray-700">{t("profiles.slidesMax")}</span>
            <input
              type="number"
              min={1}
              value={form.slide_max}
              onChange={(e) => set("slide_max", Number(e.target.value))}
              className="input-field"
            />
          </label>
        </div>

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-gray-700">{t("studio.language")}</span>
          <input
            value={form.language}
            onChange={(e) => set("language", e.target.value)}
            className="input-field md:max-w-xs"
          />
        </label>

        <div className="flex flex-col gap-2 text-sm border-t border-gray-100 pt-5 mt-2">
          <span className="font-medium text-gray-700">{t("profiles.sectionStructure")}</span>
          <SectionStructureBuilder
            value={form.section_structure as Array<{ title: string }>}
            onChange={(next) => set("section_structure", next)}
          />
        </div>

        <label className="flex flex-col gap-1.5 text-sm border-t border-gray-100 pt-5 mt-2">
          <span className="font-medium text-gray-700">{t("profiles.promptConfig")}</span>
          <textarea
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            rows={4}
            placeholder={t("profiles.promptPlaceholder")}
            className="input-field font-mono text-xs leading-relaxed"
          />
        </label>

        {error && (
          <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-600 flex items-start gap-3 mt-2">
            <svg className="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <p>{error}</p>
          </div>
        )}

        <div className="flex items-center gap-3 pt-4 mt-2 border-t border-gray-100 justify-end">
          <button type="button" onClick={onCancel} className="btn-ghost">
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            disabled={saving || form.template_id === ""}
            className="btn-primary min-w-[140px]"
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                {t("profiles.saving")}
              </span>
            ) : editing ? (
              t("profiles.saveNewVersion")
            ) : (
              t("profiles.createProfile")
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
