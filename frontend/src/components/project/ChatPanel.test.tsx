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
    truncated: false,
  },
];

function renderPanel(props: Partial<Parameters<typeof ChatPanel>[0]> = {}) {
  return render(
    <LocaleProvider>
      <ChatPanel
        projectId="p1"
        pendingQuestion={null}
        onConsumed={() => {}}
        {...props}
      />
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

const FAKE_OUTLINE = {
  id: "o1",
  project_id: "p1",
  profile_id: null,
  profile_version: null,
  schema_version: "1.0",
  content: {
    schema_version: "1.0",
    sections: [{ id: "s1", title: "Ringkasan", order: 0 }],
    talking_points: [{ section_id: "s1", text: "Poin pertama" }],
    data_bindings: [],
  },
  valid: true,
  created_at: new Date().toISOString(),
};

describe("ChatPanel generation trigger (DG-1/DG-2: outline-first)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "listChat").mockResolvedValue(ANSWERED as never);
    stubSessions();
  });

  it("opens the outline setup card on the explicit /generate command", async () => {
    // Arrange
    const user = userEvent.setup();
    const send = vi.spyOn(api, "sendChat");
    renderPanel();

    // Act
    await user.type(screen.getByPlaceholderText(/Tanyakan tentang sumber Anda/i), "/generate{Enter}");

    // Assert -- a card appears and NO message was sent; nothing outline/generation
    // related fired until a deliberate click on "Buat kerangka"
    expect(await screen.findByRole("form", { name: "Buat slide" })).toBeInTheDocument();
    expect(send).not.toHaveBeenCalled();
  });

  it("never treats ordinary prose as a request to build an outline or generate", async () => {
    // Arrange -- the exact failure mode intent detection would have: a user musing
    // about slides must not spend quota.
    const user = userEvent.setup();
    const buildOutline = vi.spyOn(api, "buildFreeformOutline");
    const createGeneration = vi.spyOn(api, "createGeneration");
    vi.spyOn(api, "sendChat").mockResolvedValue(ANSWERED[0] as never);
    renderPanel();

    // Act
    await user.type(
      screen.getByPlaceholderText(/Tanyakan tentang sumber Anda/i),
      "bisakah kamu ringkas ini seperti presentasi?{Enter}",
    );

    // Assert -- sent as a question; nothing billable fired, no card opened
    await waitFor(() => expect(api.sendChat).toHaveBeenCalled());
    expect(buildOutline).not.toHaveBeenCalled();
    expect(createGeneration).not.toHaveBeenCalled();
    expect(screen.queryByRole("form", { name: "Buat slide" })).not.toBeInTheDocument();
  });

  it("requires building and confirming an outline before anything is generated", async () => {
    // Arrange
    const user = userEvent.setup();
    const buildOutline = vi
      .spyOn(api, "buildFreeformOutline")
      .mockResolvedValue(FAKE_OUTLINE as never);
    const updateOutline = vi.spyOn(api, "updateOutline").mockResolvedValue(FAKE_OUTLINE as never);
    const createGeneration = vi
      .spyOn(api, "createGeneration")
      .mockResolvedValue({ id: "g1" } as never);
    renderPanel();

    // Act -- opening the card must not build or generate anything yet
    await user.click(screen.getByRole("button", { name: "Hasilkan slide" })); // the ＋ opener
    await screen.findByRole("form", { name: "Buat slide" });
    expect(buildOutline).not.toHaveBeenCalled();

    // Building the outline is the first deliberate step -- cheap, reversible
    await user.click(screen.getByRole("button", { name: "Buat kerangka" }));
    await waitFor(() => expect(buildOutline).toHaveBeenCalledTimes(1));
    expect(createGeneration).not.toHaveBeenCalled();

    // The outline review card replaces the setup card in place
    await screen.findByRole("form", { name: "Kerangka" });

    // Only the second, deliberate confirmation actually generates
    await user.click(screen.getByRole("button", { name: "Hasilkan dek" }));

    // Assert -- the third arg carries the tone/density/language/template chosen
    // during setup through to the actual render (DG-2); this only pins which
    // outline and project it fired for, not every knob's default value.
    await waitFor(() => expect(updateOutline).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(createGeneration).toHaveBeenCalledWith("p1", "o1", expect.any(Object)),
    );
  });
});

describe("ChatPanel truncation (F1)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubSessions();
  });

  const TRUNCATED = [
    {
      id: "m-trunc",
      role: "assistant" as const,
      content: "Revenue grew 12% YoY, driven mainly by",
      citations: [],
      created_at: new Date().toISOString(),
      truncated: true,
    },
  ];

  it("shows the truncation notice and a continue action only when truncated", async () => {
    // Arrange -- a complete message shows nothing
    vi.spyOn(api, "listChat").mockResolvedValue(ANSWERED as never);
    renderPanel();
    await screen.findByText(ANSWERED[0].content);

    // Assert
    expect(screen.queryByText(/terpotong/i)).not.toBeInTheDocument();
  });

  it("continuing appends to the SAME bubble and clears the notice", async () => {
    // Arrange
    vi.spyOn(api, "listChat").mockResolvedValue(TRUNCATED as never);
    const grown = {
      ...TRUNCATED[0],
      content: `${TRUNCATED[0].content} the launch of the new product line.`,
      truncated: false,
    };
    const continueChat = vi.spyOn(api, "continueChat").mockResolvedValue(grown as never);
    const user = userEvent.setup();
    renderPanel();
    await screen.findByText(/terpotong/i);

    // Act
    await user.click(screen.getByRole("button", { name: "Lanjutkan" }));

    // Assert -- the same message id was continued, not a new one created
    await waitFor(() => expect(continueChat).toHaveBeenCalledWith("m-trunc"));
    expect(await screen.findByText(grown.content)).toBeInTheDocument();
    expect(screen.queryByText(/terpotong/i)).not.toBeInTheDocument();
  });
});

describe("ChatPanel reader (F4)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    stubSessions();
  });

  it("collapses a long answer and opens the reader on request", async () => {
    // Arrange -- comfortably over the 1200-char collapse threshold
    const longAnswer = {
      id: "m-long",
      role: "assistant" as const,
      content: "Ringkasan panjang. ".repeat(100),
      citations: [],
      created_at: new Date().toISOString(),
      truncated: false,
    };
    vi.spyOn(api, "listChat").mockResolvedValue([longAnswer] as never);
    const onOpenReader = vi.fn();
    const user = userEvent.setup();
    renderPanel({ onOpenReader });

    // Act
    const seeMore = await screen.findByRole("button", { name: "Lihat selengkapnya" });
    await user.click(seeMore);

    // Assert -- the FULL message (not the truncated preview) is handed to the opener
    expect(onOpenReader).toHaveBeenCalledWith(expect.objectContaining({ id: "m-long" }));
    const opened = onOpenReader.mock.calls[0][0];
    expect(opened.content).toBe(longAnswer.content);
  });

  it("does not offer 'see more' for an ordinary short answer", async () => {
    // Arrange
    vi.spyOn(api, "listChat").mockResolvedValue(ANSWERED as never);
    renderPanel();
    await screen.findByText(ANSWERED[0].content);

    // Assert
    expect(screen.queryByRole("button", { name: "Lihat selengkapnya" })).not.toBeInTheDocument();
  });
});
