/**
 * Markdown rendering for AI-authored text.
 *
 * Chat replies and the notebook summary shipped showing literal `**bold**` and `-`
 * bullets, because the UI printed model output inside a plain `<p>`. It read as a
 * model defect — the reported instinct was to switch models — but no model change
 * could have fixed it. These tests pin the rendering, and pin that raw HTML in model
 * output is NOT rendered, since that text derives from user-uploaded documents.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "@/components/ui/Markdown";

describe("Markdown", () => {
  it("renders bold as an element, not as asterisks", () => {
    // Arrange / Act
    render(<Markdown>{"**Panduan Onboarding BRImerchant** menjelaskan prosesnya."}</Markdown>);

    // Assert
    const bold = screen.getByText("Panduan Onboarding BRImerchant");
    expect(bold.tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument();
  });

  it("renders list markers as a real list", () => {
    // Arrange / Act
    const { container } = render(
      <Markdown>{"Langkah:\n\n- Verifikasi dokumen\n- Aktivasi EDC\n- Eskalasi keluhan"}</Markdown>,
    );

    // Assert
    expect(container.querySelectorAll("li")).toHaveLength(3);
    expect(screen.getByText("Aktivasi EDC").tagName).toBe("LI");
  });

  it("renders headings and numbered lists", () => {
    // Arrange / Act
    const { container } = render(<Markdown>{"## Ringkasan\n\n1. Satu\n2. Dua"}</Markdown>);

    // Assert
    expect(screen.getByText("Ringkasan").tagName).toMatch(/^H[1-6]$/);
    expect(container.querySelector("ol")).not.toBeNull();
  });

  it("does not render raw HTML from model output", () => {
    // Arrange -- model text derives from uploaded documents, so it is untrusted.
    const { container } = render(
      <Markdown>{'<img src=x onerror="alert(1)"> <b>not bold</b>'}</Markdown>,
    );

    // Assert -- no live elements were created; the markup stays inert text
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
  });

  it("opens model-authored links without leaking the opener", () => {
    // Arrange / Act
    render(<Markdown>{"[BRI](https://bri.co.id)"}</Markdown>);

    // Assert
    const link = screen.getByRole("link", { name: "BRI" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("keeps wide tables inside their own scroll box", () => {
    // Arrange -- a table must never widen the chat column (Phase A: only lists scroll)
    const { container } = render(
      <Markdown>{"| a | b |\n| - | - |\n| 1 | 2 |"}</Markdown>,
    );

    // Assert
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(table?.parentElement?.className).toContain("overflow-x-auto");
  });
});
