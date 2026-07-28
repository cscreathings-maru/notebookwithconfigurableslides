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
