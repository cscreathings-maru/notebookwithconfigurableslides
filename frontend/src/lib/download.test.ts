/**
 * T-2.5 / T-1.5: saving an authenticated artifact.
 *
 * `window.open()` cannot fetch a bearer-authenticated endpoint -- navigation sends no
 * Authorization header -- so downloads go through fetch + an object URL. The revoke
 * matters: without it every download leaks a blob for the life of the document.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { saveBlob } from "@/lib/download";

afterEach(() => {
  vi.useRealTimers();
});

describe("saveBlob", () => {
  it("names the file via the download attribute", () => {
    // Arrange
    const clicks: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      clicks.push(this.download);
    });

    // Act
    saveBlob(new Blob(["x"]), "deck-abc.pptx");

    // Assert
    expect(clicks).toEqual(["deck-abc.pptx"]);
  });

  it("points the anchor at an object URL for the blob", () => {
    // Arrange
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:generated");
    const hrefs: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      hrefs.push(this.getAttribute("href") ?? "");
    });
    const blob = new Blob(["x"]);

    // Act
    saveBlob(blob, "deck.pptx");

    // Assert
    expect(create).toHaveBeenCalledWith(blob);
    expect(hrefs).toEqual(["blob:generated"]);
  });

  it("removes the anchor it added", () => {
    // Arrange
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const before = document.body.childElementCount;

    // Act
    saveBlob(new Blob(["x"]), "deck.pptx");

    // Assert -- no orphaned anchors accumulate across downloads
    expect(document.body.childElementCount).toBe(before);
  });

  it("revokes the object URL once the click has been dispatched", () => {
    // Arrange
    vi.useFakeTimers();
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:generated");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    // Act
    saveBlob(new Blob(["x"]), "deck.pptx");

    // Assert -- deferred, so revoking cannot race the click
    expect(revoke).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(revoke).toHaveBeenCalledWith("blob:generated");
  });
});
