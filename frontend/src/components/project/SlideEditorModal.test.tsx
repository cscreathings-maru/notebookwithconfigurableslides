/**
 * T-2.5: URL resolution in the editor launcher — the surface T-1.2 broke.
 *
 * **Updated for T-1.2.** The modal no longer resolves anything: the backend composes
 * the URL from the engine's presentation id and the component renders it verbatim.
 * The old rewriting logic keyed off `NEXT_PUBLIC_PRESENTON_UI_URL`, which
 * `frontend/Dockerfile` never declared as a build arg -- so it was always `undefined`
 * and the rewriting was dead compensation for a value that never arrived.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SlideEditorModal } from "@/components/project/SlideEditorModal";

function renderModal(props: Partial<Parameters<typeof SlideEditorModal>[0]> = {}) {
  const onClose = vi.fn();
  render(<SlideEditorModal isOpen onClose={onClose} {...props} />);
  return onClose;
}

function launchHref(): string {
  return screen.getByRole("link").getAttribute("href") ?? "";
}

describe("visibility", () => {
  it("renders nothing when closed", () => {
    // Arrange / Act
    render(<SlideEditorModal isOpen={false} onClose={vi.fn()} />);

    // Assert
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders the launcher when open", () => {
    // Arrange / Act
    renderModal();

    // Assert
    expect(screen.getByRole("link")).toBeInTheDocument();
  });
});

describe("url resolution", () => {
  it("defaults to the same-origin editor root", () => {
    // Arrange / Act
    renderModal();

    // Assert
    expect(launchHref()).toBe("/editor/");
  });

  it("passes an absolute url through untouched", () => {
    // Arrange / Act
    renderModal({ editorUrl: "https://editor.example.com/presentation/abc" });

    // Assert
    expect(launchHref()).toBe("https://editor.example.com/presentation/abc");
  });

  it("keeps a root-relative url relative", () => {
    // Arrange -- with no base URL configured, same-origin is the intended result
    renderModal({ editorUrl: "/editor/presentation/abc" });

    // Assert
    expect(launchHref()).toBe("/editor/presentation/abc");
  });

  it("uses the backend URL verbatim", () => {
    // Arrange -- T-1.2: the backend composes this from the ENGINE's presentation id,
    // so any client-side rewriting would corrupt a URL that is already correct.
    renderModal({ editorUrl: "/editor/presentation?id=abc-123" });

    // Assert
    expect(launchHref()).toBe("/editor/presentation?id=abc-123");
  });

  it("does not rewrite a legacy /presenton path", () => {
    // Arrange -- the old rewriting logic keyed off NEXT_PUBLIC_PRESENTON_UI_URL, which
    // frontend/Dockerfile never declared as a build arg, so it was always undefined and
    // rewrote nothing. Deleted in T-1.2 rather than left as dead compensation.
    renderModal({ editorUrl: "/presenton/presentation/abc" });

    // Assert
    expect(launchHref()).toBe("/presenton/presentation/abc");
  });

  it("shows the resolved url to the user", () => {
    // Arrange -- the modal displays the target before launching
    renderModal({ editorUrl: "/editor/presentation/xyz" });

    // Assert
    expect(screen.getByText("/editor/presentation/xyz")).toBeInTheDocument();
  });
});

describe("launch safety", () => {
  it("opens in a new tab without leaking the opener", () => {
    // Arrange / Act
    renderModal();
    const link = screen.getByRole("link");

    // Assert
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
