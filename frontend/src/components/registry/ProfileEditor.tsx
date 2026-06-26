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
    language: "en",
    section_structure: [],
    prompt_config: {},
  };
}

export function ProfileEditor({ templates, editing, onSaved, onCancel }: Props) {
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
      setError(err instanceof ApiError ? err.message : "Failed to save profile");
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
          {editing ? `Edit “${editing.name}” → new version` : "New profile"}
        </h2>
        <button type="button" onClick={onCancel} className="text-sm text-ink/50 hover:text-ink">
          Cancel
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Name</span>
          <input
            required
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
            className={inputCls}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Template</span>
          <select
            value={form.template_id}
            onChange={(e) => set("template_id", e.target.value)}
            className={inputCls}
          >
            {templates.length === 0 && <option value="">No approved templates</option>}
            {templates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} (v{t.version})
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/60">Audience</span>
        <input
          required
          value={form.audience}
          onChange={(e) => set("audience", e.target.value)}
          placeholder="e.g. Group management, technical, non-technical"
          className={inputCls}
        />
      </label>

      <div className="grid grid-cols-4 gap-4">
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Tone</span>
          <select value={form.tone} onChange={(e) => set("tone", e.target.value as Tone)} className={inputCls}>
            {TONES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Verbosity</span>
          <select
            value={form.verbosity}
            onChange={(e) => set("verbosity", e.target.value as Verbosity)}
            className={inputCls}
          >
            {VERBOSITIES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Slides min</span>
          <input
            type="number"
            min={1}
            value={form.slide_min}
            onChange={(e) => set("slide_min", Number(e.target.value))}
            className={inputCls}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-ink/60">Slides max</span>
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
        <span className="text-ink/60">Language</span>
        <input
          value={form.language}
          onChange={(e) => set("language", e.target.value)}
          className={`${inputCls} max-w-32`}
        />
      </label>

      <div className="flex flex-col gap-2 text-sm">
        <span className="text-ink/60">Required section structure (ordered)</span>
        <SectionStructureBuilder
          value={form.section_structure as Array<{ title: string }>}
          onChange={(next) => set("section_structure", next)}
        />
      </div>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-ink/60">Prompt config (system)</span>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          rows={3}
          placeholder="Controlled prompt guidance / exemplars"
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
        {saving ? "Saving…" : editing ? "Save as new version" : "Create profile"}
      </button>
    </form>
  );
}
