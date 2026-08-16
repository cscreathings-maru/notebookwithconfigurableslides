/**
 * T-2.5: the Studio download branch — the surface T-1.5 changed.
 *
 * Downloads moved from `window.open(url)` to an authenticated blob fetch plus
 * `saveBlob`. That change touched three components; the typechecker caught two of
 * them, but nothing asserted the behaviour. These tests pin it.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StudioPanel } from "@/components/project/StudioPanel";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { api, ApiError } from "@/services/api";
import { id as messages } from "@/lib/i18n/messages/id";

vi.mock("@/lib/download", () => ({ saveBlob: vi.fn() }));
const { saveBlob } = await import("@/lib/download");

const READY_DECK = {
  id: "gen-1",
  project_id: "p1",
  status: "ready",
  artifacts: { pptx: true, pdf: true },
  params: {},
  source_ids: [],
  created_at: new Date().toISOString(),
};

const FAILED_DECK = {
  ...READY_DECK,
  id: "gen-2",
  status: "failed",
  artifacts: { pptx: false, pdf: false },
  error: "Consistency check failed; deck flagged for review.",
  consistency_report: {
    passed: false,
    checks: [
      { name: "artifact_readable", passed: true, detail: {} },
      { name: "slide_count_in_range", passed: false, detail: { n_slides: 3, min: 4 } },
    ],
  },
};

function stubApi(overrides: Partial<typeof api> = {}) {
  vi.spyOn(api, "listGenerations").mockResolvedValue([READY_DECK] as never);
  vi.spyOn(api, "listTemplates").mockResolvedValue([] as never);
  vi.spyOn(api, "listModels").mockResolvedValue([] as never);
  for (const [name, impl] of Object.entries(overrides)) {
    vi.spyOn(api, name as keyof typeof api).mockImplementation(impl as never);
  }
}

function renderPanel() {
  render(
    <LocaleProvider>
      <StudioPanel projectId="p1" />
    </LocaleProvider>,
  );
}

async function clickDownload(format: "pptx" | "pdf") {
  const label = new RegExp(format, "i");
  const button = await screen.findByRole("button", { name: label });
  await userEvent.click(button);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("deck download", () => {
  it("saves the fetched bytes instead of navigating", async () => {
    // Arrange
    const blob = new Blob(["PPTX"]);
    stubApi();
    const download = vi.spyOn(api, "downloadGeneration").mockResolvedValue(blob);

    // Act
    renderPanel();
    await clickDownload("pptx");

    // Assert -- a bearer-authenticated URL cannot be reached by navigation
    await waitFor(() => expect(download).toHaveBeenCalledWith("gen-1", "pptx"));
    expect(saveBlob).toHaveBeenCalledWith(blob, "deck-gen-1.pptx");
  });

  it("names the file by format", async () => {
    // Arrange
    stubApi();
    vi.spyOn(api, "downloadGeneration").mockResolvedValue(new Blob(["PDF"]));

    // Act
    renderPanel();
    await clickDownload("pdf");

    // Assert
    await waitFor(() =>
      expect(saveBlob).toHaveBeenCalledWith(expect.any(Blob), "deck-gen-1.pdf"),
    );
  });

  it("surfaces an error instead of failing silently", async () => {
    // Arrange
    stubApi();
    vi.spyOn(api, "downloadGeneration").mockRejectedValue(
      new ApiError(404, "not_found", "No pptx artifact."),
    );

    // Act
    renderPanel();
    await clickDownload("pptx");

    // Assert -- the standing instruction: make failure visible
    await waitFor(() =>
      expect(screen.getByText(messages["studio.downloadUnavailable"]!)).toBeInTheDocument(),
    );
    expect(saveBlob).not.toHaveBeenCalled();
  });

  it("does not save anything when the download fails", async () => {
    // Arrange
    stubApi();
    vi.spyOn(api, "downloadGeneration").mockRejectedValue(new Error("network"));

    // Act
    renderPanel();
    await clickDownload("pptx");

    // Assert
    await waitFor(() => expect(saveBlob).not.toHaveBeenCalled());
  });
});

describe("Studio uses the outline-first flow, not the old one-shot form", () => {
  it("renders OutlineBuilderCard's setup card instead of a direct Generate button", async () => {
    // Arrange -- pins the fix: Studio's tab previously rendered its own
    // content-source/tone/density/slides form with a single "Generate deck"
    // button that skipped straight to a billable action. It now embeds the same
    // picker -> outline -> confirm flow chat uses -- generation is never one click.
    stubApi();
    vi.spyOn(api, "listLanguages").mockResolvedValue([]);

    // Act
    renderPanel();

    // Assert -- the outline-first "build" action is present...
    expect(await screen.findByRole("button", { name: /Buat kerangka/ })).toBeInTheDocument();
    // ...and confirming a deck (the review phase's action) is not reachable
    // before an outline exists -- there is no one-shot "generate now" button.
    expect(screen.queryByRole("button", { name: /Hasilkan dek/ })).not.toBeInTheDocument();
  });
});

describe("RM-13: the Presenton editor is gone", () => {
  it("offers no editor button -- there is no external studio to open", async () => {
    // Arrange -- the deck renders in-process now (RM-11), so there is no
    // engine-side presentation to hand off to. A button that opened one would
    // point at a service that no longer exists.
    stubApi();
    vi.spyOn(api, "listLanguages").mockResolvedValue([]);

    // Act
    renderPanel();
    await screen.findByRole("button", { name: /PPTX/ });

    // Assert
    expect(screen.queryByRole("button", { name: /Editor/ })).not.toBeInTheDocument();
  });
});

describe("failed decks explain themselves", () => {
  it("shows the error and which consistency checks tripped", async () => {
    // Arrange -- a failed deck used to render the single word "failed"; the
    // reason was on the wire the whole time and nothing displayed it.
    vi.spyOn(api, "listGenerations").mockResolvedValue([FAILED_DECK] as never);
    vi.spyOn(api, "listTemplates").mockResolvedValue([] as never);
    vi.spyOn(api, "listModels").mockResolvedValue([] as never);
    vi.spyOn(api, "listLanguages").mockResolvedValue([]);

    // Act
    renderPanel();

    // Assert -- the backend's own message, plus the named failing check
    expect(await screen.findByText(/Consistency check failed/)).toBeInTheDocument();
    expect(
      screen.getByText(messages["consistency.slide_count_in_range"]!),
    ).toBeInTheDocument();
    // ...and only the FAILING check is listed, not the passing one.
    expect(
      screen.queryByText(messages["consistency.artifact_readable"]!),
    ).not.toBeInTheDocument();
  });
});

describe("download actions are reachable without hover", () => {
  it("renders download buttons visibly, not gated behind group-hover", async () => {
    // Arrange -- these were `opacity-0 group-hover:opacity-100`, which on a
    // touch device made the finished deck unreachable entirely.
    stubApi();
    vi.spyOn(api, "listLanguages").mockResolvedValue([]);

    // Act
    renderPanel();

    // Assert
    const button = await screen.findByRole("button", { name: /PPTX/ });
    expect(button).toBeVisible();
    expect(button.closest(".opacity-0")).toBeNull();
  });
});

describe("LD-9: the per-deck review gate is retired", () => {
  const STALE_PARKED = {
    ...READY_DECK,
    id: "gen-3",
    status: "awaiting_review",
    artifacts: { pptx: false, pdf: false },
  };

  it("shows a stale-state message instead of a dead review button", async () => {
    // Arrange -- `awaiting_review` is vestigial (module docstring): no new
    // generation ever lands here, since the review gate moved to the
    // template's catalog (L3). A pre-cutover row stuck at this status has no
    // action left to take -- the old approve endpoint is gone -- so this
    // must say so rather than pointing at a dead flow.
    vi.spyOn(api, "listGenerations").mockResolvedValue([STALE_PARKED] as never);
    vi.spyOn(api, "listTemplates").mockResolvedValue([] as never);
    vi.spyOn(api, "listModels").mockResolvedValue([] as never);
    vi.spyOn(api, "listLanguages").mockResolvedValue([]);

    // Act
    renderPanel();

    // Assert
    expect(await screen.findByText(/tidak dapat dilanjutkan/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Periksa tata letak/ })).not.toBeInTheDocument();
    // ...and no download, because nothing was ever rendered.
    expect(screen.queryByRole("button", { name: /PPTX/ })).not.toBeInTheDocument();
  });
});
