/**
 * T-2.5: URL resolution in the editor launcher — the surface T-1.2 broke.
 *
 * These pin the *current* behaviour so the T-1.2 fix (which needs the vendored
 * Presenton source and is still blocked as TD-06) has a baseline to change against.
 * They already prove one half of T-1.2's diagnosis: `NEXT_PUBLIC_PRESENTON_UI_URL`
 * is never declared as a build arg in `frontend/Dockerfile`, so Next.js inlines it
 * as `undefined` and `defaultBaseUrl` is permanently "". The rewriting logic built
 * on it is dead code compensating for a value that never arrives.
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

  it("prefixes a bare path with a slash", () => {
    // Arrange / Act
    renderModal({ editorUrl: "editor/presentation/abc" });

    // Assert
    expect(launchHref()).toBe("/editor/presentation/abc");
  });

  it("rewrites the legacy /presenton prefix to /editor", () => {
    // Arrange -- left over from the retired subdomain model
    renderModal({ editorUrl: "/presenton/presentation/abc" });

    // Assert
    expect(launchHref()).toBe("/editor/presentation/abc");
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
