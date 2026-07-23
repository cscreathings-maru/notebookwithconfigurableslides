/**
 * English messages — the source of truth for i18n keys.
 *
 * `id.ts` mirrors these keys; any key missing there falls back to English, so a
 * new key added here will never render as a raw key. Use {var} placeholders for
 * interpolation (see the `t(key, vars)` signature).
 */

export const en = {
  // Generic
  "common.cancel": "Cancel",
  "common.create": "Create",
  "common.edit": "Edit",
  "common.approve": "Approve",

  // App chrome
  "app.loadingSession": "Loading session…",
  "nav.tenant": "Tenant",
  "nav.signOut": "Sign out",
  "nav.language": "Language",
  "nav.openSidebar": "Open sidebar",
  "nav.closeSidebar": "Close sidebar",
  "nav.projects": "Projects",
  "nav.profiles": "Profiles",
  "nav.templates": "Templates",
  "nav.usage": "Usage & Audit",
  "nav.llm": "LLM Provider",

  // Login
  "login.title": "Sign in",
  "login.subtitle": "Presentation Notebook LLM orchestration console.",
  "login.sso": "Continue with SSO",
  "login.failed": "Login failed",
  "login.devTokenLabel": "Dev token (OIDC_DEV_MODE)",
  "login.devTokenPlaceholder": "Paste an HS256 dev token",
  "login.useDevToken": "Use dev token",

  // Projects list
  "projects.title": "Projects",
  "projects.subtitle":
    "A project maps to a notebook. Upload sources, build an outline, then generate a deck.",
  "projects.newName": "New project name",
  "projects.createFailed": "Failed to create project",
  "projects.empty": "No projects yet.",

  // Project workspace
  "workspace.back": "← Projects",
  "workspace.fallbackName": "Notebook",
  "workspace.subtitle":
    "Upload sources, explore them with an auto guide and chat, then generate configurable slides.",

  // Sources
  "sources.title": "Sources",
  "sources.addUrl": "Add URL",
  "sources.urlPlaceholder": "https://…",
  "sources.uploadFailed": "Upload failed",
  "sources.addUrlFailed": "Add URL failed",
  "sources.empty": "No sources yet.",

  // Guide
  "guide.title": "Notebook guide",
  "guide.generate": "Generate",
  "guide.regenerate": "Regenerate",
  "guide.generating": "Generating…",
  "guide.failed": "Could not generate the guide.",
  "guide.empty": "Once your sources are ready, generate an overview and starter questions.",
  "guide.reading": "Reading your sources…",
  "guide.tryAsking": "Try asking",

  // Chat
  "chat.title": "Chat with your sources",
  "chat.empty": "Ask a question grounded in your sources.",
  "chat.thinking": "Thinking…",
  "chat.failed": "Chat failed.",
  "chat.placeholder": "Ask about your sources…",
  "chat.send": "Send",
  "chat.cite": "cite",

  // Studio
  "studio.title": "Studio — generate slides",
  "studio.contentSource": "Content source",
  "studio.source.summary": "Notebook summary",
  "studio.source.notebook": "Synthesized sources",
  "studio.source.chat": "Latest chat answer",
  "studio.source.custom": "Custom markdown",
  "studio.customPlaceholder": "## Slide title\n- point one\n- point two",
  "studio.tone": "Tone",
  "studio.density": "Density",
  "studio.slides": "Slides",
  "studio.output": "Output",
  "studio.template": "Template",
  "studio.defaultTheme": "Default theme",
  "studio.model": "Model",
  "studio.language": "Language",
  "studio.webSearch": "Web search grounding",
  "studio.generate": "Generate deck",
  "studio.starting": "Starting…",
  "studio.decks": "Decks",
  "studio.noDecks": "No decks yet.",
  "studio.slidesUnit": "slides",
  "studio.askChatFirst": "Ask something in chat first.",
  "studio.startFailed": "Could not start generation.",
  "studio.downloadUnavailable": "Download unavailable.",

  // Tone options
  "tone.default": "default",
  "tone.casual": "casual",
  "tone.professional": "professional",
  "tone.funny": "funny",
  "tone.educational": "educational",
  "tone.sales_pitch": "sales pitch",

  // Density / verbosity options
  "density.concise": "concise",
  "density.standard": "standard",
  "density.text-heavy": "text-heavy",

  // Source status
  "status.source.queued": "queued",
  "status.source.processing": "processing",
  "status.source.ready": "ready",
  "status.source.failed": "failed",

  // Generation status
  "status.gen.queued": "queued",
  "status.gen.analyzing": "analyzing",
  "status.gen.building_outline": "building outline",
  "status.gen.generating": "generating",
  "status.gen.validating": "validating",
  "status.gen.ready": "ready",
  "status.gen.failed": "failed",

  // Registry status
  "status.registry.draft": "draft",
  "status.registry.approved": "approved",
  "status.registry.archived": "archived",

  // Templates
  "templates.title": "Templates",
  "templates.subtitle":
    "Company templates that pin brand and structure for generation. Import a PPTX to register it with the generation engine.",
  "templates.adminOnly": "Templates are managed by tenant admins.",
  "templates.new": "New template",
  "templates.name": "Name",
  "templates.primaryColor": "Primary color",
  "templates.font": "Font",
  "templates.importPptx": "Import PPTX (optional)",
  "templates.creating": "Creating…",
  "templates.create": "Create template",
  "templates.createFailed": "Failed to create template",
  "templates.approveFailed": "Approve failed",
  "templates.colVersion": "Version",
  "templates.colPptx": "PPTX",
  "templates.colStatus": "Status",
  "templates.imported": "imported",
  "templates.empty": "No templates yet.",

  // Profiles
  "profiles.adminOnly": "Profiles are managed by tenant admins.",
  "profiles.title": "Stakeholder profiles",
  "profiles.subtitle":
    "Audience profiles that drive consistent, on-brand generation. Editing creates a new immutable version.",
  "profiles.new": "New profile",
  "profiles.approveFailed": "Approve failed",
  "profiles.colAudience": "Audience",
  "profiles.colSlides": "Slides",
  "profiles.empty": "No profiles yet.",
  "profiles.editVersion": "Edit “{name}” → new version",
  "profiles.saveFailed": "Failed to save profile",
  "profiles.audience": "Audience",
  "profiles.audiencePlaceholder": "e.g. Group management, technical, non-technical",
  "profiles.verbosity": "Verbosity",
  "profiles.slidesMin": "Slides min",
  "profiles.slidesMax": "Slides max",
  "profiles.sectionStructure": "Required section structure (ordered)",
  "profiles.promptConfig": "Prompt config (system)",
  "profiles.promptPlaceholder": "Controlled prompt guidance / exemplars",
  "profiles.noApprovedTemplates": "No approved templates",
  "profiles.saving": "Saving…",
  "profiles.saveNewVersion": "Save as new version",
  "profiles.createProfile": "Create profile",
  "sections.titlePlaceholder": "Section title",
  "sections.moveUp": "Move up",
  "sections.moveDown": "Move down",
  "sections.remove": "Remove section",
  "sections.add": "+ Add section",

  // Usage
  "usage.adminOnly": "Usage & audit are visible to tenant admins.",
  "usage.title": "Usage & audit",
  "usage.subtitle": "Who generated what, token spend, and the full audit trail.",
  "usage.from": "From",
  "usage.to": "To",
  "usage.loadFailed": "Failed to load usage. Admin role required.",
  "usage.generations": "Generations",
  "usage.tokensIn": "Tokens in",
  "usage.tokensOut": "Tokens out",
  "usage.estCost": "Est. cost",
  "usage.byUser": "By user",
  "usage.colUser": "User",
  "usage.noUsage": "No usage in range.",
  "usage.auditLog": "Audit log",
  "usage.colWhen": "When",
  "usage.colAction": "Action",
  "usage.colResource": "Resource",
  "usage.noAudit": "No audit events in range.",
  "usage.system": "system",
  "usage.quotaTitle": "Monthly quota",
  "usage.quotaUnlimited": "unlimited",
  "usage.quotaUsed": "{used} / {limit} used",
  "usage.quotaReached": "Quota reached — new generations are blocked.",
  "usage.quotaRemaining": "{remaining} generations remaining this month",
} as const;

export type MessageKey = keyof typeof en;
