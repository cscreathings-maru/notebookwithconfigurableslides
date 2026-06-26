/**
 * Typed orchestrator API client.
 *
 * Single entry point for every backend call: attaches the bearer token, parses
 * the consistent { error: { code, message } } shape, and surfaces a typed
 * ApiError. The browser only ever talks to this public surface.
 */

import { config } from "@/lib/config";
import { getToken } from "@/services/session";

export type Role = "admin" | "author" | "viewer";

export interface Me {
  user: { id: string; email: string; role: Role; status: string };
  tenant: { id: string; name: string; slug: string; status: string; region: string | null };
  role: Role;
}

export interface Job {
  id: string;
  type: "ingest" | "generate";
  status: "queued" | "running" | "succeeded" | "failed";
  progress: Record<string, unknown>;
  attempts: number;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  // Let the browser set the multipart boundary for FormData uploads.
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${config.apiBase}${path}`, { ...init, headers });

  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText;
    try {
      const body = await res.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export type RegistryStatus = "draft" | "approved" | "archived";
export type Tone =
  | "default"
  | "casual"
  | "professional"
  | "funny"
  | "educational"
  | "sales_pitch";
export type Verbosity = "concise" | "standard" | "text-heavy";

export interface Template {
  id: string;
  version: number;
  name: string;
  brand_tokens: Record<string, unknown>;
  status: RegistryStatus;
  has_pptx: boolean;
  created_at: string;
}

export interface Profile {
  id: string;
  version: number;
  name: string;
  audience: string;
  template_id: string;
  template_version: number;
  tone: Tone;
  verbosity: Verbosity;
  slide_min: number;
  slide_max: number;
  language: string;
  section_structure: Array<Record<string, unknown>>;
  prompt_config: Record<string, unknown>;
  status: RegistryStatus;
  created_at: string;
}

export interface ProfileInput {
  name: string;
  audience: string;
  template_id: string;
  tone: Tone;
  verbosity: Verbosity;
  slide_min: number;
  slide_max: number;
  language: string;
  section_structure: Array<Record<string, unknown>>;
  prompt_config: Record<string, unknown>;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export type SourceStatus = "queued" | "processing" | "ready" | "failed";

export interface Source {
  id: string;
  project_id: string;
  kind: string;
  name: string;
  status: SourceStatus;
  error: string | null;
  created_at: string;
}

export interface OutlineSection {
  id: string;
  title: string;
  order: number;
}

export interface OutlineContent {
  schema_version: string;
  sections: OutlineSection[];
  talking_points: Array<{ section_id: string; text: string }>;
  data_bindings: Array<Record<string, unknown>>;
}

export interface Outline {
  id: string;
  project_id: string;
  profile_id: string;
  profile_version: number;
  schema_version: string;
  content: OutlineContent;
  valid: boolean;
  created_at: string;
}

export type GenerationStatus =
  | "queued"
  | "analyzing"
  | "building_outline"
  | "generating"
  | "validating"
  | "ready"
  | "failed";

export interface ConsistencyReport {
  passed: boolean;
  checks: Array<{ name: string; passed: boolean; detail: Record<string, unknown> }>;
}

export interface Generation {
  id: string;
  project_id: string | null;
  outline_id: string | null;
  status: GenerationStatus;
  profile_version: number;
  template_version: number;
  model: string | null;
  provider: string | null;
  params: Record<string, unknown>;
  source_ids: string[];
  consistency_report: ConsistencyReport | null;
  artifacts: { pptx: boolean; pdf: boolean };
  error: string | null;
  created_by: string | null;
  created_at: string;
}

export interface UsageRollup {
  generations: number;
  tokens_in: number;
  tokens_out: number;
  cost_estimate: string | number;
}

export interface UserUsage extends UsageRollup {
  user_id: string | null;
  email: string | null;
}

export interface QuotaStatus {
  monthly_limit: number;
  used_this_month: number;
  remaining: number | null;
}

export interface UsageReport {
  from_: string;
  to: string;
  tenant: UsageRollup;
  quota: QuotaStatus;
  per_user: UserUsage[];
}

export interface AuditEvent {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource: Record<string, unknown>;
  created_at: string;
}

function rangeQuery(from?: string, to?: string): string {
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  me: () => request<Me>("/auth/me"),
  getJob: (id: string) => request<Job>(`/jobs/${id}`),

  // --- Usage & audit (admin) ---
  getUsage: (from?: string, to?: string) =>
    request<UsageReport>(`/usage${rangeQuery(from, to)}`),
  getAudit: (from?: string, to?: string) =>
    request<AuditEvent[]>(`/audit${rangeQuery(from, to)}`),

  // --- Projects, sources ---
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (name: string) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify({ name }) }),
  listSources: (projectId: string) => request<Source[]>(`/projects/${projectId}/sources`),
  uploadSource: (projectId: string, input: { file?: File | null; url?: string }) => {
    const form = new FormData();
    if (input.file) form.set("file", input.file);
    if (input.url) form.set("url", input.url);
    return request<Source>(`/projects/${projectId}/sources`, { method: "POST", body: form });
  },

  // --- Outline ---
  buildOutline: (projectId: string, profileId: string) =>
    request<Outline>(`/projects/${projectId}/outline`, {
      method: "POST",
      body: JSON.stringify({ profile_id: profileId }),
    }),
  getOutline: (id: string) => request<Outline>(`/outlines/${id}`),
  updateOutline: (id: string, content: OutlineContent) =>
    request<Outline>(`/outlines/${id}`, { method: "PUT", body: JSON.stringify({ content }) }),

  // --- Generation ---
  createGeneration: (projectId: string, outlineId: string) =>
    request<Generation>(`/projects/${projectId}/generations`, {
      method: "POST",
      body: JSON.stringify({ outline_id: outlineId }),
    }),
  getGeneration: (id: string) => request<Generation>(`/generations/${id}`),
  listGenerations: (projectId: string) =>
    request<Generation[]>(`/projects/${projectId}/generations`),
  downloadGeneration: (id: string, format: "pptx" | "pdf") =>
    request<{ format: string; url: string; expires_in: number }>(
      `/generations/${id}/download?format=${format}`,
    ),
  setLlmConfig: (input: {
    provider: string;
    base_url: string;
    model: string;
    api_key: string;
  }) =>
    request<{ provider: string; base_url: string; model: string }>("/tenant/llm-config", {
      method: "PUT",
      body: JSON.stringify(input),
    }),

  // --- Templates ---
  listTemplates: () => request<Template[]>("/templates"),
  createTemplate: (input: { name: string; brand_tokens: Record<string, unknown>; pptx?: File | null }) => {
    const form = new FormData();
    form.set("name", input.name);
    form.set("brand_tokens", JSON.stringify(input.brand_tokens ?? {}));
    if (input.pptx) form.set("file", input.pptx);
    return request<Template>("/templates", { method: "POST", body: form });
  },
  approveTemplate: (id: string) =>
    request<Template>(`/templates/${id}/approve`, { method: "POST" }),

  // --- Profiles ---
  listProfiles: () => request<Profile[]>("/profiles"),
  createProfile: (input: ProfileInput) =>
    request<Profile>("/profiles", { method: "POST", body: JSON.stringify(input) }),
  updateProfile: (id: string, input: ProfileInput) =>
    request<Profile>(`/profiles/${id}`, { method: "PUT", body: JSON.stringify(input) }),
  approveProfile: (id: string) =>
    request<Profile>(`/profiles/${id}/approve`, { method: "POST" }),
};
