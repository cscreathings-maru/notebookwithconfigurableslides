/**
 * DG-3: the template picker's filter, and that a selected template actually
 * reaches the generation request. StudioPanel's equivalent filter bug (approved
 * templates that had fallen back to the stock theme still appeared as a choice)
 * is what DG-3.1 fixed; these pin the fix on this component too.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OutlineBuilderCard } from "@/components/project/OutlineBuilderCard";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { api } from "@/services/api";

const REGISTERED_TEMPLATE = {
  id: "tpl-good",
  version: 1,
  name: "Corporate",
  brand_tokens: {},
  status: "approved",
  has_pptx: true,
  registration_status: "registered",
  registration_error: null,
  preview_url: "/editor/template-preview?id=x",
  thumbnail_urls: ["/app_data/corporate-1.png"],
  created_at: new Date().toISOString(),
};

const FALLEN_BACK_TEMPLATE = {
  ...REGISTERED_TEMPLATE,
  id: "tpl-broken",
  name: "Broken Brand",
  status: "approved",
  registration_status: "fallback",
  thumbnail_urls: [],
};

const FAKE_OUTLINE = {
  id: "o1",
  project_id: "p1",
  profile_id: null,
  profile_version: null,
  schema_version: "1.0",
  content: {
    schema_version: "1.0",
    sections: [{ id: "s1", title: "Overview", order: 0 }],
    talking_points: [],
    data_bindings: [],
  },
  valid: true,
  created_at: new Date().toISOString(),
};

function stubApi() {
  vi.spyOn(api, "listTemplates").mockResolvedValue([
    REGISTERED_TEMPLATE,
    FALLEN_BACK_TEMPLATE,
  ] as never);
  vi.spyOn(api, "listModels").mockResolvedValue([]);
  vi.spyOn(api, "listLanguages").mockResolvedValue([]);
}

function renderCard() {
  render(
    <LocaleProvider>
      <OutlineBuilderCard
        projectId="p1"
        onCancel={() => {}}
        onGenerated={() => {}}
      />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("template picker", () => {
  it("offers only templates the engine actually registered", async () => {
    // Arrange
    stubApi();

    // Act
    renderCard();

    // Assert -- the registered one appears, the fallen-back one does not
    expect(await screen.findByRole("button", { name: /Corporate/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Broken Brand/ })).not.toBeInTheDocument();
  });

  it("carries the selected template through to the generation request", async () => {
    // Arrange
    const user = userEvent.setup();
    stubApi();
    vi.spyOn(api, "buildFreeformOutline").mockResolvedValue(FAKE_OUTLINE as never);
    vi.spyOn(api, "updateOutline").mockResolvedValue(FAKE_OUTLINE as never);
    const createGeneration = vi
      .spyOn(api, "createGeneration")
      .mockResolvedValue({ id: "g1" } as never);
    renderCard();

    // Act -- select the template, build the outline, confirm
    const templateButton = await screen.findByRole("button", { name: /Corporate/ });
    await user.click(templateButton);
    await user.click(screen.getByRole("button", { name: /Buat kerangka/ }));
    await screen.findByRole("form", { name: /Kerangka/ });
    await user.click(screen.getByRole("button", { name: /Hasilkan dek/ }));

    // Assert
    await waitFor(() =>
      expect(createGeneration).toHaveBeenCalledWith(
        "p1",
        "o1",
        expect.objectContaining({ template_id: "tpl-good" }),
      ),
    );
  });

  it("defaults to no template (the stock theme) until one is picked", async () => {
    // Arrange
    const user = userEvent.setup();
    stubApi();
    vi.spyOn(api, "buildFreeformOutline").mockResolvedValue(FAKE_OUTLINE as never);
    vi.spyOn(api, "updateOutline").mockResolvedValue(FAKE_OUTLINE as never);
    const createGeneration = vi
      .spyOn(api, "createGeneration")
      .mockResolvedValue({ id: "g1" } as never);
    renderCard();

    // Act -- no template click at all
    await screen.findByRole("button", { name: /Corporate/ }); // wait for templates to load
    await user.click(screen.getByRole("button", { name: /Buat kerangka/ }));
    await screen.findByRole("form", { name: /Kerangka/ });
    await user.click(screen.getByRole("button", { name: /Hasilkan dek/ }));

    // Assert
    await waitFor(() =>
      expect(createGeneration).toHaveBeenCalledWith(
        "p1",
        "o1",
        expect.objectContaining({ template_id: undefined }),
      ),
    );
  });
});
