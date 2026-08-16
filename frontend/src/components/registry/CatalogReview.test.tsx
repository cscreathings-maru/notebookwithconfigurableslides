/**
 * LD-4 / L3: the per-template catalog review gate.
 *
 * What matters: every design (usable or not) is shown with its reason, an
 * edit to role/purpose is captured before approving, and approving always
 * sends the full corrected design list -- never a silent partial that could
 * drop a design the admin never touched.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CatalogReview } from "@/components/registry/CatalogReview";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { api } from "@/services/api";

const CATALOG = {
  schema_version: "1.0",
  designs: [
    {
      design_id: "slide-0",
      slide_index: 0,
      role: "cover",
      capacity: 0,
      anchors: [{ anchor_id: "265", current_text: "[Presentation Title]", purpose: "title", char_budget: 60 }],
      usable: true,
      reason: null,
    },
    {
      design_id: "slide-29",
      slide_index: 29,
      role: "logo_library",
      capacity: 0,
      anchors: [],
      usable: false,
      reason: "no anchors this renderer can address were identified",
    },
  ],
};

function renderReview(overrides: Partial<Parameters<typeof CatalogReview>[0]> = {}) {
  return render(
    <LocaleProvider>
      <CatalogReview
        templateId="tpl-1"
        onDone={overrides.onDone ?? (() => {})}
        onCancel={overrides.onCancel ?? (() => {})}
      />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("catalog review", () => {
  it("shows every design, including unusable ones with their reason", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockResolvedValue(CATALOG as never);

    renderReview();

    expect(await screen.findByText(/Slide 1/)).toBeInTheDocument();
    expect(screen.getByText(/Slide 30/)).toBeInTheDocument();
    expect(screen.getByText(/no anchors this renderer can address/)).toBeInTheDocument();
  });

  it("shows the anchor's current text next to its editable purpose", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockResolvedValue(CATALOG as never);

    renderReview();

    expect(await screen.findByText("[Presentation Title]")).toBeInTheDocument();
    expect(screen.getByDisplayValue("title")).toBeInTheDocument();
  });

  it("approving with no edits still sends the full design list", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockResolvedValue(CATALOG as never);
    const review = vi.spyOn(api, "reviewTemplateCatalog").mockResolvedValue({} as never);
    const user = userEvent.setup();

    renderReview();
    await screen.findByText(/Slide 1/);
    await user.click(screen.getByRole("button", { name: /Setujui katalog/ }));

    await waitFor(() => expect(review).toHaveBeenCalledWith("tpl-1", CATALOG.designs));
  });

  it("sends an edited role/purpose back on approve", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockResolvedValue(CATALOG as never);
    const review = vi.spyOn(api, "reviewTemplateCatalog").mockResolvedValue({} as never);
    const user = userEvent.setup();

    renderReview();
    const roleInput = await screen.findByDisplayValue("cover");
    await user.clear(roleInput);
    await user.type(roleInput, "title_slide");
    await user.click(screen.getByRole("button", { name: /Setujui katalog/ }));

    await waitFor(() => {
      const [, sentDesigns] = review.mock.calls[0] as [string, typeof CATALOG.designs];
      expect(sentDesigns[0].role).toBe("title_slide");
    });
  });

  it("calls back on success so the caller can refresh the template list", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockResolvedValue(CATALOG as never);
    vi.spyOn(api, "reviewTemplateCatalog").mockResolvedValue({} as never);
    const onDone = vi.fn();
    const user = userEvent.setup();

    renderReview({ onDone });
    await screen.findByText(/Slide 1/);
    await user.click(screen.getByRole("button", { name: /Setujui katalog/ }));

    await waitFor(() => expect(onDone).toHaveBeenCalled());
  });

  it("surfaces an approve failure instead of closing silently", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockResolvedValue(CATALOG as never);
    vi.spyOn(api, "reviewTemplateCatalog").mockRejectedValue(new Error("boom"));
    const onDone = vi.fn();
    const user = userEvent.setup();

    renderReview({ onDone });
    await screen.findByText(/Slide 1/);
    await user.click(screen.getByRole("button", { name: /Setujui katalog/ }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("surfaces a load failure rather than rendering an empty shell", async () => {
    vi.spyOn(api, "getTemplateCatalog").mockRejectedValue(new Error("network"));

    renderReview();

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
