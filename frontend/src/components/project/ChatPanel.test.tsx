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

import { render, screen, waitFor, within } from "@testing-library/react";
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

const SESSION_A = {
  id: "s-a",
  project_id: "p1",
  title: "Onboarding merchant",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};
const SESSION_B = { ...SESSION_A, id: "s-b", title: "Harga paket" };

function stubSessions(sessions = [SESSION_A, SESSION_B]) {
  vi.spyOn(api, "listChatSessions").mockResolvedValue(sessions as never);
}

describe("ChatPanel citations", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listChat").mockResolvedValue(ANSWERED as never);
    stubSessions([]);
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

describe("ChatPanel sessions", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listChat").mockResolvedValue([] as never);
    stubSessions();
  });

  it("shows the active session and lets the user switch threads", async () => {
    // Arrange
    const user = userEvent.setup();
    renderPanel();
    expect(await screen.findByRole("button", { name: /Onboarding merchant/ })).toBeInTheDocument();

    // Act -- open the switcher and pick the other thread
    await user.click(screen.getByRole("button", { name: /Onboarding merchant/ }));
    const options = await screen.findAllByRole("option");
    await user.click(within(options[1]).getByRole("button", { name: "Harga paket" }));

    // Assert -- the thread was reloaded scoped to the chosen session
    await waitFor(() =>
      expect(api.listChat).toHaveBeenCalledWith("p1", expect.objectContaining({ sessionId: "s-b" })),
    );
  });

  it("offers undo after deleting a thread and restores it", async () => {
    // Arrange -- delete is an archive server-side, so undo brings the messages back
    const user = userEvent.setup();
    vi.spyOn(api, "deleteChatSession").mockResolvedValue(SESSION_A as never);
    const restore = vi.spyOn(api, "restoreChatSession").mockResolvedValue(SESSION_A as never);
    renderPanel();

    // Act
    await user.click(await screen.findByRole("button", { name: /Onboarding merchant/ }));
    await user.click(screen.getByRole("button", { name: /Hapus: Onboarding merchant/ }));

    // Assert -- undo is offered, and taking it calls restore
    const undo = await screen.findByRole("button", { name: "Urungkan" });
    await user.click(undo);
    await waitFor(() => expect(restore).toHaveBeenCalledWith("s-a"));
  });
});

describe("ChatPanel generation trigger", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listChat").mockResolvedValue(ANSWERED as never);
    stubSessions();
  });

  it("opens the confirmation card on the explicit /generate command", async () => {
    // Arrange
    const user = userEvent.setup();
    const send = vi.spyOn(api, "sendChat");
    renderPanel();

    // Act
    await user.type(screen.getByPlaceholderText(/Tanyakan tentang sumber Anda/i), "/generate{Enter}");

    // Assert -- a card appears and NO message was sent
    expect(await screen.findByRole("form", { name: "Hasilkan slide" })).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });

  it("never treats ordinary prose as a request to generate", async () => {
    // Arrange -- the exact failure mode intent detection would have: a user musing
    // about slides must not spend quota.
    const user = userEvent.setup();
    const generate = vi.spyOn(api, "generateDeck");
    vi.spyOn(api, "sendChat").mockResolvedValue(ANSWERED[0] as never);
    renderPanel();

    // Act
    await user.type(
      screen.getByPlaceholderText(/Tanyakan tentang sumber Anda/i),
      "bisakah kamu ringkas ini seperti presentasi?{Enter}",
    );

    // Assert -- sent as a question; nothing billable fired, no card opened
    await waitFor(() => expect(api.sendChat).toHaveBeenCalled());
    expect(generate).not.toHaveBeenCalled();
    expect(screen.queryByRole("form", { name: "Hasilkan slide" })).not.toBeInTheDocument();
  });

  it("requires a second, deliberate click before anything is generated", async () => {
    // Arrange
    const user = userEvent.setup();
    const generate = vi.spyOn(api, "generateDeck").mockResolvedValue({ id: "g1" } as never);
    renderPanel();

    // Act -- opening the card must not generate
    await user.click(screen.getByRole("button", { name: "Hasilkan slide" }));  // the ＋ opener
    await screen.findByRole("form", { name: "Hasilkan slide" });
    expect(generate).not.toHaveBeenCalled();

    // Only confirming does
    await user.click(screen.getByRole("button", { name: "Hasilkan" }));

    // Assert
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
  });
});
