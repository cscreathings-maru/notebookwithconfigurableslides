/**
 * TM-4/TM-5/TM-6: the templates page had zero tests before this (noted in the
 * original engineering assessment as a 0/10 frontend gap). Pins the rewrite:
 * no brand-token configurator, no manual approve button, delete requires a
 * second confirming click, and a .pptx is required to create a template.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TemplatesPage from "@/app/(app)/templates/page";
import { LocaleProvider } from "@/lib/i18n/LocaleProvider";
import { api, ApiError } from "@/services/api";

vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({
    me: { user: { id: "u1", email: "admin@acme.id", role: "admin", status: "active" }, tenant: { id: "t1", name: "Acme", slug: "acme", status: "active", region: null }, role: "admin" },
    loading: false,
    error: null,
    signOut: vi.fn(),
  }),
}));

const READY = {
  id: "tpl-1",
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

function renderPage() {
  return render(
    <LocaleProvider>
      <TemplatesPage />
    </LocaleProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("no brand-token configurator (TM-6)", () => {
  it("the create form asks only for a name and a .pptx file", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([]);

    // Act -- the header's opener button; the empty-state row has one with the
    // same accessible name, so this scopes to the first (header) instance.
    renderPage();
    await userEvent.click((await screen.findAllByRole("button", { name: /New template|Templat baru/i }))[0]);

    // Assert -- no colour pickers, no font select, no logo/aspect-ratio fields
    expect(screen.queryByText(/Primary Color|Primary color/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Logo URL/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Aspect Ratio/i)).not.toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Q4 Executive Report/i)).toBeInTheDocument();
  });

  it("refuses to submit without a .pptx", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([]);
    const create = vi.spyOn(api, "createTemplate");
    const user = userEvent.setup();

    // Act
    renderPage();
    await user.click((await screen.findAllByRole("button", { name: /New template|Templat baru/i }))[0]);
    await user.type(screen.getByPlaceholderText(/Q4 Executive Report/i), "No File Template");
    const submit = screen.getByRole("button", { name: /Create template|Buat templat/i });

    // Assert -- the submit button itself stays disabled without a file
    expect(submit).toBeDisabled();
    expect(create).not.toHaveBeenCalled();
  });
});

describe("no manual approve step (TM-4)", () => {
  it("never renders an Approve button", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([READY] as never);

    // Act
    renderPage();
    await screen.findByText("Corporate");

    // Assert
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });
});

describe("delete requires a second confirming click (TM-5)", () => {
  it("does not delete on the first click", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([READY] as never);
    const del = vi.spyOn(api, "deleteTemplate").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Corporate");

    // Act
    await user.click(screen.getByRole("button", { name: /^Delete$|^Hapus$/i }));

    // Assert
    expect(del).not.toHaveBeenCalled();
    expect(await screen.findByRole("button", { name: /Confirm delete|Konfirmasi hapus/i })).toBeInTheDocument();
  });

  it("deletes on the second click", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([READY] as never);
    const del = vi.spyOn(api, "deleteTemplate").mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Corporate");

    // Act
    await user.click(screen.getByRole("button", { name: /^Delete$|^Hapus$/i }));
    await user.click(await screen.findByRole("button", { name: /Confirm delete|Konfirmasi hapus/i }));

    // Assert
    await waitFor(() => expect(del).toHaveBeenCalledWith("tpl-1"));
  });

  it("surfaces the 409 in-use message instead of failing silently", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([READY] as never);
    vi.spyOn(api, "deleteTemplate").mockRejectedValue(
      new ApiError(409, "version_in_use", "This template is used by an existing generation and cannot be deleted."),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Corporate");

    // Act
    await user.click(screen.getByRole("button", { name: /^Delete$|^Hapus$/i }));
    await user.click(await screen.findByRole("button", { name: /Confirm delete|Konfirmasi hapus/i }));

    // Assert -- pins the fix: the error alert previously only rendered inside the
    // (closed) create form, so a delete/reregister failure had nowhere to show.
    expect(
      await screen.findByText(/used by an existing generation and cannot be deleted/i),
    ).toBeInTheDocument();
  });
});

describe("catalog status badges (LD-3/LD-4)", () => {
  it("a reviewed, ready template shows both catalog-ready and reviewed", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([READY] as never);

    // Act
    renderPage();
    await screen.findByText("Corporate");

    // Assert
    expect(await screen.findByText(/Catalog ready|Katalog siap/)).toBeInTheDocument();
    expect(screen.getByText(/Reviewed|Sudah ditinjau/)).toBeInTheDocument();
  });

  it("a failed catalog shows the cataloguing error inline", async () => {
    // Arrange -- the reason was previously tooltip-only on the old inspection
    // badge, which is how a whole class of failure went unnoticed for months.
    vi.spyOn(api, "listTemplates").mockResolvedValue([
      {
        ...READY,
        id: "tpl-2",
        status: "draft",
        catalog_status: "failed",
        catalog_error: "LLM returned an unparseable design catalog.",
        catalog_reviewed: false,
      },
    ] as never);

    // Act
    renderPage();
    await screen.findByText("Corporate");

    // Assert
    expect(
      screen.getByText(/LLM returned an unparseable design catalog/),
    ).toBeInTheDocument();
  });

  it("offers re-catalogue on a failed template that still has its .pptx", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([
      { ...READY, catalog_status: "failed", catalog_error: "nope", catalog_reviewed: false },
    ] as never);

    // Act
    renderPage();
    await screen.findByText("Corporate");

    // Assert
    expect(
      screen.getByRole("button", { name: /Re-catalogue|Buat ulang katalog/i }),
    ).toBeInTheDocument();
  });

  it("offers review, not re-catalogue, on a healthy template", async () => {
    // Arrange
    vi.spyOn(api, "listTemplates").mockResolvedValue([READY] as never);

    // Act
    renderPage();
    await screen.findByText("Corporate");

    // Assert
    expect(
      screen.queryByRole("button", { name: /Re-catalogue|Buat ulang katalog/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Review catalog|Tinjau katalog/i })).toBeInTheDocument();
  });
});
