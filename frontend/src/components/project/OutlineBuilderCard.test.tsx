/**
 * The template picker's filter, and that a selected template actually reaches
 * the generation request.
 *
 * RM-11 made a template mandatory: slides render into the chosen template's own
 * layouts, so there is no stock theme to fall back to and the backend refuses a
 * generation without one. The picker therefore has no "default theme" option
 * and gates the build action instead of letting the user reach Generate and
 * collect a 422.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OutlineBuilderCard } from "@/components/project/OutlineBuilderCard";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { api } from "@/services/api";

/** Default to a non-admin author -- the common case, and the one whose
 *  no-template message differs (an author cannot reach /templates). */
const mockRole = { current: "author" };
vi.mock("@/components/AuthProvider", () => ({
  useOptionalAuth: () => ({
    me: { user: { id: "u1", email: "a@b.c", role: mockRole.current, status: "active" }, role: mockRole.current },
    loading: false,
    error: null,
    signOut: vi.fn(),
  }),
}));

const READY_TEMPLATE = {
  id: "tpl-good",
  version: 1,
  name: "Corporate",
  brand_tokens: {},
  status: "approved",
  has_pptx: true,
  catalog_status: "ready",
  catalog_error: null,
  catalog_reviewed: true,
  created_at: new Date().toISOString(),
};

/** A second usable template, so the picker has a real choice to make and the
 *  single-template auto-select does not fire. */
const SECOND_READY_TEMPLATE = {
  ...READY_TEMPLATE,
  id: "tpl-other",
  name: "Minimal",
};

/** Not yet reviewed (L3) -- `status` stays `draft`, so `isSelectableTemplate`
 *  excludes it from the picker the same way a rejected inspection used to. */
const UNREVIEWED_TEMPLATE = {
  ...READY_TEMPLATE,
  id: "tpl-unreviewed",
  name: "Unreviewed Brand",
  status: "draft",
  catalog_reviewed: false,
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

function stubApi(templates: unknown[] = [READY_TEMPLATE, SECOND_READY_TEMPLATE, UNREVIEWED_TEMPLATE]) {
  vi.spyOn(api, "listTemplates").mockResolvedValue(templates as never);
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
  it("offers only templates a deck can actually be rendered from", async () => {
    // Arrange
    stubApi();

    // Act
    renderCard();

    // Assert -- the approved ones appear, the unreviewed one does not
    expect(await screen.findByRole("button", { name: /Corporate/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Minimal/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Unreviewed Brand/ })).not.toBeInTheDocument();
  });

  it("offers no stock-theme option -- rendering requires a real template", async () => {
    // Arrange
    stubApi();

    // Act
    renderCard();
    await screen.findByRole("button", { name: /Corporate/ });

    // Assert -- "Default theme"/"Tema bawaan" used to sit at the head of this
    // list; picking it now produces a backend 422, so it is gone.
    expect(screen.queryByRole("button", { name: /Tema bawaan|Default theme/ })).not.toBeInTheDocument();
  });

  it("blocks building until a template is chosen", async () => {
    // Arrange -- two usable templates, so there is a real choice and the
    // single-template auto-select does not fire.
    stubApi([READY_TEMPLATE, SECOND_READY_TEMPLATE]);

    // Act
    renderCard();
    await screen.findByRole("button", { name: /Corporate/ });

    // Assert -- gated at the START of the flow, not after an outline has been
    // built and reviewed for nothing.
    expect(screen.getByRole("button", { name: /Buat kerangka/ })).toBeDisabled();
  });

  it("auto-selects when there is only one template -- no choice to make", async () => {
    // Arrange
    const user = userEvent.setup();
    stubApi([READY_TEMPLATE]);
    vi.spyOn(api, "buildFreeformOutline").mockResolvedValue(FAKE_OUTLINE as never);
    vi.spyOn(api, "updateOutline").mockResolvedValue(FAKE_OUTLINE as never);
    const createGeneration = vi
      .spyOn(api, "createGeneration")
      .mockResolvedValue({ id: "g1" } as never);

    // Act -- never click the template
    renderCard();
    await screen.findByRole("button", { name: /Corporate/ });
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

  it("tells a non-admin to ask an admin, not to visit an admin-only page", async () => {
    // Arrange -- the blocking state. /templates is admin-only, so linking an
    // author there lands them on "managed by tenant admins" and no further.
    mockRole.current = "author";
    stubApi([UNREVIEWED_TEMPLATE]);

    // Act
    renderCard();

    // Assert
    expect(await screen.findByText(/Belum ada templat yang dapat dipakai/)).toBeInTheDocument();
    expect(screen.getByText(/Minta admin workspace mengunggah/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("links an admin straight to the upload page", async () => {
    // Arrange
    mockRole.current = "admin";
    stubApi([UNREVIEWED_TEMPLATE]);

    // Act
    renderCard();

    // Assert
    expect(await screen.findByText(/Belum ada templat yang dapat dipakai/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Unggah berkas .pptx/ })).toHaveAttribute(
      "href",
      "/templates",
    );
    mockRole.current = "author"; // restore for any later test
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

  it("sends no removed fields -- web_search and export_as are gone", async () => {
    // Arrange -- `web_search` was silently ignored by the backend and
    // `export_as: "pdf"` was rejected outright at the last step (RM-14 is
    // unbuilt). Both controls are gone; this pins that they stay gone.
    const user = userEvent.setup();
    stubApi([READY_TEMPLATE]);
    vi.spyOn(api, "buildFreeformOutline").mockResolvedValue(FAKE_OUTLINE as never);
    vi.spyOn(api, "updateOutline").mockResolvedValue(FAKE_OUTLINE as never);
    const createGeneration = vi
      .spyOn(api, "createGeneration")
      .mockResolvedValue({ id: "g1" } as never);

    // Act
    renderCard();
    await screen.findByRole("button", { name: /Corporate/ });
    await user.click(screen.getByRole("button", { name: /Buat kerangka/ }));
    await screen.findByRole("form", { name: /Kerangka/ });
    await user.click(screen.getByRole("button", { name: /Hasilkan dek/ }));

    // Assert
    await waitFor(() => expect(createGeneration).toHaveBeenCalled());
    const config = createGeneration.mock.calls[0][2] ?? {};
    expect(config).not.toHaveProperty("web_search");
    expect(config).not.toHaveProperty("export_as");
  });
});
