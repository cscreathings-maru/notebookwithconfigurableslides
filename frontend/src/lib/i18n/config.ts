/**
 * Locale configuration for the lightweight context-based i18n.
 *
 * `id` (Bahasa Indonesia) is the default — the product targets Indonesian users.
 * `en` is the fallback and the source of truth for message keys. Language *names*
 * (not codes) are what the AI-content backend expects (Presenton, guide/chat).
 */

export type Locale = "id" | "en";

export const DEFAULT_LOCALE: Locale = "id";

export const LOCALES: { code: Locale; label: string }[] = [
  { code: "id", label: "Bahasa Indonesia" },
  { code: "en", label: "English" },
];

/** Map a UI locale to the language NAME sent to the AI-content backend. */
export const localeToLanguageName: Record<Locale, string> = {
  id: "Bahasa Indonesia",
  en: "English",
};
