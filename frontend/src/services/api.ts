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

/** Attach auth, send, and turn a non-2xx into an ApiError. Response body untouched. */
async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
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

  return res;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  const res = await authorizedFetch(path, { ...init, headers });

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Binary variant. Artifacts stream through the API behind the same bearer token, so
 *  they cannot be fetched by navigation (`window.open`) -- that sends no Authorization. */
async function requestBlob(path: string, init: RequestInit = {}): Promise<Blob> {
  const res = await authorizedFetch(path, init);
  return await res.blob();
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

/** Whether the slide engine accepted this template. `fallback` means decks render
 *  with the engine's stock theme, not the uploaded branding. */
export type RegistrationStatus = "registered" | "fallback" | "failed";

export interface Template {
  id: string;
  version: number;
  name: string;
  brand_tokens: Record<string, unknown>;
  status: RegistryStatus;
  has_pptx: boolean;
  registration_status: RegistrationStatus;
  registration_error: string | null;
  /** Same-origin link to preview this template's layouts in the slide editor,
   *  composed by the backend from the ENGINE's template id. `null` when the engine
   *  never accepted the template, so there is nothing to preview. */
  preview_url: string | null;
  created_at: string;
}

export interface ExtractedTokensResponse {
  status: string;
  filename: string;
  extracted_tokens: {
    primary_color: string;
    secondary_color: string;
    accent_color: string;
    typography: string;
    aspect_ratio: string;
    detected_fonts?: string[];
    detected_colors?: string[];
  };
  confidence_score: number;
  summary: string;
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
  profile_version: number | null;
  template_version: number | null;
  model: string | null;
  provider: string | null;
  params: Record<string, unknown>;
  source_ids: string[];
  consistency_report: ConsistencyReport | null;
  artifacts: { pptx: boolean; pdf: boolean };
  /** Same-origin link that opens this deck in the slide editor, composed by the
   *  backend. `null` when there is nothing to open -- the engine has not produced a
   *  presentation for this generation yet (T-1.2). */
  editor_url: string | null;
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

// --- NotebookLM-style: guide, chat, studio ---

export type GuideStatus = "pending" | "ready" | "failed";

export interface Guide {
  project_id: string;
  summary: string | null;
  suggested_questions: string[];
  status: GuideStatus;
  error: string | null;
  updated_at: string;
}

export type ChatRole = "user" | "assistant";

export interface Citation {
  source_ref: string | null;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  citations: Citation[];
  created_at: string;
  // True when the provider stopped on the token cap, not because the answer was
  // finished. Always false for user turns. `continueChat` appends the rest.
  truncated: boolean;
}

/** One named thread within a project. `title` is null until the first question. */
export interface ChatSession {
  id: string;
  project_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatPage {
  /** Omit to target the project's most recent session (created on demand). */
  sessionId?: string;
  limit?: number;
  /** ISO timestamp cursor: return turns strictly older than this. */
  before?: string;
}

export interface ModelOption {
  id: string;
  default: boolean;
}

export interface LanguageOption {
  id: string;
  default: boolean;
}

export type ContentSource = "summary" | "notebook" | "chat" | "custom";

export interface DeckConfig {
  content_source: ContentSource;
  custom_markdown?: string;
  chat_message_id?: string;
  tone: Tone;
  density: Verbosity;
  n_slides: number;
  template_id?: string | null;
  web_search: boolean;
  model?: string;
  export_as: "pptx" | "pdf";
  // AI output language NAME (e.g. "Bahasa Indonesia"); omit → server default.
  language?: string;
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

  // --- Guide (auto notebook overview) ---
  getGuide: (projectId: string) => request<Guide>(`/projects/${projectId}/guide`),
  regenerateGuide: (projectId: string) =>
    request<Guide>(`/projects/${projectId}/guide`, { method: "POST" }),

  // --- Chat with sources (RAG + citations) ---
  listChat: (projectId: string, page: ChatPage = {}) => {
    const params = new URLSearchParams();
    if (page.sessionId) params.set("session_id", page.sessionId);
    if (page.limit !== undefined) params.set("limit", String(page.limit));
    if (page.before) params.set("before", page.before);
    const qs = params.toString();
    return request<ChatMessage[]>(`/projects/${projectId}/chat${qs ? `?${qs}` : ""}`);
  },
  sendChat: (projectId: string, question: string, sessionId?: string) =>
    request<ChatMessage>(`/projects/${projectId}/chat`, {
      method: "POST",
      body: JSON.stringify(sessionId ? { question, session_id: sessionId } : { question }),
    }),
  // Appends the rest of a truncated answer, in place -- returns the SAME message id
  // with grown content, not a new message.
  continueChat: (messageId: string) =>
    request<ChatMessage>(`/chat/messages/${messageId}/continue`, { method: "POST" }),

  // --- Chat sessions (named threads within a project) ---
  listChatSessions: (projectId: string) =>
    request<ChatSession[]>(`/projects/${projectId}/chat/sessions`),
  createChatSession: (projectId: string, title?: string) =>
    request<ChatSession>(`/projects/${projectId}/chat/sessions`, {
      method: "POST",
      body: JSON.stringify({ title: title ?? null }),
    }),
  renameChatSession: (sessionId: string, title: string) =>
    request<ChatSession>(`/chat/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    }),
  // Soft delete: the thread is hidden but every message survives for `restore`.
  deleteChatSession: (sessionId: string) =>
    request<ChatSession>(`/chat/sessions/${sessionId}`, { method: "DELETE" }),
  restoreChatSession: (sessionId: string) =>
    request<ChatSession>(`/chat/sessions/${sessionId}/restore`, { method: "POST" }),

  // --- Models (OpenRouter dropdown) ---
  listModels: () => request<ModelOption[]>("/models"),

  // --- Languages (AI output language dropdown) ---
  listLanguages: () => request<LanguageOption[]>("/languages"),

  // --- Generation ---
  createGeneration: (projectId: string, outlineId: string) =>
    request<Generation>(`/projects/${projectId}/generations`, {
      method: "POST",
      body: JSON.stringify({ outline_id: outlineId }),
    }),
  // Freeform (Studio) deck generation with per-deck config.
  generateDeck: (projectId: string, config: DeckConfig) =>
    request<Generation>(`/projects/${projectId}/generations`, {
      method: "POST",
      body: JSON.stringify(config),
    }),
  getGeneration: (id: string) => request<Generation>(`/generations/${id}`),
  listGenerations: (projectId: string) =>
    request<Generation[]>(`/projects/${projectId}/generations`),
  downloadGeneration: (id: string, format: "pptx" | "pdf") =>
    requestBlob(`/generations/${id}/download?format=${format}`),
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
  extractTemplateTokens: (file: File) => {
    const form = new FormData();
    form.set("file", file);
    return request<ExtractedTokensResponse>("/templates/extract-tokens", { method: "POST", body: form });
  },
  approveTemplate: (id: string) =>
    request<Template>(`/templates/${id}/approve`, { method: "POST" }),
  /** Retry engine registration from the template's already-stored PPTX. Repairs
   *  templates whose registration failed; no re-upload needed. */
  reregisterTemplate: (id: string) =>
    request<Template>(`/templates/${id}/reregister`, { method: "POST" }),

  // --- Profiles ---
  listProfiles: () => request<Profile[]>("/profiles"),
  createProfile: (input: ProfileInput) =>
    request<Profile>("/profiles", { method: "POST", body: JSON.stringify(input) }),
  updateProfile: (id: string, input: ProfileInput) =>
    request<Profile>(`/profiles/${id}`, { method: "PUT", body: JSON.stringify(input) }),
  approveProfile: (id: string) =>
    request<Profile>(`/profiles/${id}/approve`, { method: "POST" }),
};
