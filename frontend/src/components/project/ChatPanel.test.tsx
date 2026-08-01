/**
 * Citation disclosure — the surface Phase A changed.
 *
 * Citations were hover-only `title` tooltips: invisible on touch, unreachable by
 * keyboard, ignored by screen readers. They are the trust surface of a RAG product,
 * so the interaction is pinned here.
 *
 * The first replacement was a floating popover, which is wrong in this component
 * specifically: the message list is an `overflow-y-auto` container, so an absolutely
 * positioned child is clipped regardless of z-index — the snippet for any message near
 * the top of the viewport was cut off. It also dismissed on a 150ms blur timer, so
 * opening a second citation while the first was closing raced and closed both. These
 * tests assert the inline-disclosure behaviour that replaced it.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatPanel } from "@/components/project/ChatPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { api } from "@/services/api";

const SNIPPET_A = "Bab 3 — Daftar BRImerchant, langkah inti registrasi.";
const SNIPPET_B = "Untuk Siapa Panduan Ini? Pemilik usaha yang mendaftar sendiri.";

const ANSWERED = [
  {
    id: "m1",
    role: "assistant" as const,
    content: "Panduan ini menjelaskan proses onboarding merchant.",
    citations: [
      { source_ref: "source:a", snippet: SNIPPET_A },
      { source_ref: "source:b", snippet: SNIPPET_B },
    ],
    created_at: new Date().toISOString(),
  },
];

function renderPanel() {
  return render(
    <LocaleProvider>
      <ChatPanel projectId="p1" pendingQuestion={null} onConsumed={() => {}} />
    </LocaleProvider>,
  );
}

describe("ChatPanel citations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listChat").mockResolvedValue(ANSWERED as never);
  });

  it("renders one activatable control per citation", async () => {
    // Arrange / Act
    renderPanel();

    // Assert -- buttons, not hover-only spans, so touch and keyboard both reach them
    const chips = await screen.findAllByRole("button", { name: /kutipan/i });
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveAttribute("aria-expanded", "false");
  });

  it("reveals the snippet inline when a citation is activated", async () => {
    // Arrange
    const user = userEvent.setup();
    renderPanel();
    const chips = await screen.findAllByRole("button", { name: /kutipan/i });

    // Act
    await user.click(chips[0]);

    // Assert -- the snippet is in the document, not hidden behind a `title` attribute
    expect(await screen.findByText(SNIPPET_A)).toBeInTheDocument();
    expect(chips[0]).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps at most one snippet open when a second citation is activated", async () => {
    // Arrange -- the case the old blur timer raced on
    const user = userEvent.setup();
    renderPanel();
    const chips = await screen.findAllByRole("button", { name: /kutipan/i });
    await user.click(chips[0]);
    expect(await screen.findByText(SNIPPET_A)).toBeInTheDocument();

    // Act
    await user.click(chips[1]);

    // Assert -- the second opens AND the first closes; neither is left half-open
    expect(await screen.findByText(SNIPPET_B)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(SNIPPET_A)).not.toBeInTheDocument());
  });

  it("closes an open snippet when the same citation is activated again", async () => {
    // Arrange
    const user = userEvent.setup();
    renderPanel();
    const chips = await screen.findAllByRole("button", { name: /kutipan/i });
    await user.click(chips[0]);
    expect(await screen.findByText(SNIPPET_A)).toBeInTheDocument();

    // Act
    await user.click(chips[0]);

    // Assert
    await waitFor(() => expect(screen.queryByText(SNIPPET_A)).not.toBeInTheDocument());
    expect(chips[0]).toHaveAttribute("aria-expanded", "false");
  });

  it("closes an open snippet on Escape", async () => {
    // Arrange
    const user = userEvent.setup();
    renderPanel();
    const chips = await screen.findAllByRole("button", { name: /kutipan/i });
    await user.click(chips[0]);
    expect(await screen.findByText(SNIPPET_A)).toBeInTheDocument();

    // Act
    await user.keyboard("{Escape}");

    // Assert
    await waitFor(() => expect(screen.queryByText(SNIPPET_A)).not.toBeInTheDocument());
  });
});
