/**
 * Workspace shell — the surface Phase B re-organised, and the one that had no tests.
 *
 * That gap is why a build breakage shipped: the tab labels called `t(key, "fallback")`
 * with keys absent from both dictionaries, so `tsc` failed and, had it built, the tabs
 * would have rendered the raw keys ("rightRail.guide", "tab.sources"). Nothing
 * exercised this page, so nothing caught it. These tests assert the structure the
 * layout depends on: real translated labels, the two-tab right rail, and the mobile
 * tab bar that replaces the three columns below `lg`.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProjectDetailPage from "@/app/(app)/projects/[id]/page";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { en, type MessageKey } from "@/lib/i18n/messages/en";
import { id as messages } from "@/lib/i18n/messages/id";
import { api } from "@/services/api";

/** `id` is a Partial map, so a missing key would silently become `undefined` here —
 *  which is the very defect these tests exist to catch. Fail loudly instead. */
function msg(key: MessageKey): string {
  const value = messages[key];
  if (!value) throw new Error(`Missing Indonesian translation for "${key}"`);
  return value;
}

function renderPage() {
  return render(
    <LocaleProvider>
      <ProjectDetailPage params={{ id: "p1" }} />
    </LocaleProvider>,
  );
}

describe("project workspace shell", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "getProject").mockResolvedValue({ id: "p1", name: "Onboarding new" } as never);
    vi.spyOn(api, "listSources").mockResolvedValue([] as never);
    vi.spyOn(api, "listChat").mockResolvedValue([] as never);
    vi.spyOn(api, "listChatSessions").mockResolvedValue([] as never);
    vi.spyOn(api, "listGenerations").mockResolvedValue([] as never);
    vi.spyOn(api, "listTemplates").mockResolvedValue([] as never);
    vi.spyOn(api, "listModels").mockResolvedValue([] as never);
    vi.spyOn(api, "listLanguages").mockResolvedValue([] as never);
    vi.spyOn(api, "getGuide").mockRejectedValue(new Error("no guide"));
  });

  it("renders the project name once loaded", async () => {
    // Arrange / Act
    renderPage();

    // Assert
    expect(await screen.findByRole("heading", { name: "Onboarding new" })).toBeInTheDocument();
  });

  it("labels every tab from the dictionary, never a raw key", async () => {
    // Arrange / Act -- the exact defect that shipped: `t()` returns the key it cannot
    // resolve, so an untranslated tab renders as "rightRail.guide".
    renderPage();
    await screen.findByRole("heading", { name: "Onboarding new" });

    // Assert
    for (const key of [
      "rightRail.guide",
      "rightRail.studio",
      "tab.sources",
      "tab.chat",
      "tab.tools",
      "workspace.openTools",
    ] as const) {
      expect(msg(key), `id is missing ${key}`).toBeTruthy();
      expect(en[key], `en is missing ${key}`).toBeTruthy();
      expect(screen.queryByText(key), `${key} leaked as a raw key`).not.toBeInTheDocument();
    }
    expect(screen.getAllByText(msg("rightRail.guide")).length).toBeGreaterThan(0);
  });

  it("switches the right rail between the guide and studio", async () => {
    // Arrange
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Onboarding new" });

    // Act
    await user.click(screen.getByRole("button", { name: msg("rightRail.studio") }));

    // Assert -- Studio replaced the guide in the shared column
    await waitFor(() =>
      expect(screen.getByText(msg("studio.title"))).toBeInTheDocument(),
    );
  });

  it("renders the three columns and the mobile tab bar", async () => {
    // Arrange / Act -- both exist in the DOM; CSS breakpoints decide which is visible,
    // so this pins the structure rather than the media query.
    renderPage();
    await screen.findByRole("heading", { name: "Onboarding new" });

    // Assert -- `getAllByText`, because the panel heading and the mobile tab label are
    // deliberately the same word ("Sumber"), so a single-match query would be wrong.
    expect(screen.getAllByText(msg("sources.title")).length).toBeGreaterThan(0);
    expect(screen.getByText(msg("chat.title"))).toBeInTheDocument();
    for (const key of ["tab.sources", "tab.chat", "tab.tools"] as const) {
      expect(screen.getAllByText(msg(key)).length).toBeGreaterThan(0);
    }
  });

  it("F4: opening a long answer from chat shows it in a Reader tab in the right rail", async () => {
    // Arrange -- ChatPanel and the right rail are SIBLINGS; the reader message has
    // to travel up to this page and back down, which is exactly the wiring a
    // ChatPanel-only test cannot exercise. No "Pembaca" tab exists until something
    // is actually opened.
    const longAnswer = {
      id: "m-long",
      role: "assistant" as const,
      content: "Kalimat panjang tentang onboarding merchant. ".repeat(60),
      citations: [],
      created_at: new Date().toISOString(),
      truncated: false,
    };
    vi.spyOn(api, "listChat").mockResolvedValue([longAnswer] as never);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Onboarding new" });
    expect(screen.queryByRole("button", { name: msg("rightRail.reader") })).not.toBeInTheDocument();

    // Act
    await user.click(await screen.findByRole("button", { name: msg("reader.seeMore") }));

    // Assert -- the tab now exists, is active, and the right rail shows the full text
    const readerTab = await screen.findByRole("button", { name: msg("rightRail.reader") });
    expect(readerTab).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(longAnswer.content.trim())).toBeInTheDocument());
  });
});
