/**
 * T-2.5: the API client is where Phase 1's defects lived, so it is covered first.
 *
 * Everything the app does passes through `request`/`requestBlob`: auth attachment,
 * the error envelope, the FormData boundary rule, and the authenticated blob download
 * added in T-1.5. None of it had a single test.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/services/api";
import { clearToken, setToken } from "@/services/session";

function mockFetch(response: Response) {
  const spy = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function lastRequestInit(spy: ReturnType<typeof vi.fn>) {
  return spy.mock.calls[0][1] as RequestInit;
}

function lastHeaders(spy: ReturnType<typeof vi.fn>): Headers {
  return lastRequestInit(spy).headers as Headers;
}

beforeEach(() => {
  clearToken();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("auth attachment", () => {
  it("sends the bearer token when a session exists", async () => {
    // Arrange
    setToken("tok-123");
    const spy = mockFetch(jsonResponse([]));

    // Act
    await api.listGenerations("p1");

    // Assert
    expect(lastHeaders(spy).get("Authorization")).toBe("Bearer tok-123");
  });

  it("omits the header entirely when there is no session", async () => {
    // Arrange
    const spy = mockFetch(jsonResponse([]));

    // Act
    await api.listGenerations("p1");

    // Assert -- an empty "Bearer " would look like a malformed token to the server
    expect(lastHeaders(spy).has("Authorization")).toBe(false);
  });
});

describe("error envelope", () => {
  it("surfaces the server's code and message", async () => {
    // Arrange
    mockFetch(
      jsonResponse({ error: { code: "quota_exceeded", message: "Monthly cap reached." } }, 429),
    );

    // Act
    const failure = api.listGenerations("p1");

    // Assert
    await expect(failure).rejects.toBeInstanceOf(ApiError);
    await expect(failure).rejects.toMatchObject({
      status: 429,
      code: "quota_exceeded",
      message: "Monthly cap reached.",
    });
  });

  it("falls back to the status text when the body is not JSON", async () => {
    // Arrange -- e.g. a proxy 502 returning HTML
    mockFetch(new Response("<html>Bad Gateway</html>", { status: 502, statusText: "Bad Gateway" }));

    // Act / Assert
    await expect(api.listGenerations("p1")).rejects.toMatchObject({
      status: 502,
      code: "http_error",
    });
  });

  it("does not treat a 2xx as an error", async () => {
    // Arrange
    mockFetch(jsonResponse([{ id: "g1" }]));

    // Act
    const result = await api.listGenerations("p1");

    // Assert
    expect(result).toEqual([{ id: "g1" }]);
  });
});

describe("request bodies", () => {
  it("sets a JSON content type for object bodies", async () => {
    // Arrange
    const spy = mockFetch(jsonResponse({ id: "p1" }));

    // Act
    await api.createProject("Acme");

    // Assert
    expect(lastHeaders(spy).get("Content-Type")).toBe("application/json");
  });

  it("leaves the content type unset for FormData", async () => {
    // Arrange -- the browser must set it, or the multipart boundary is lost
    const spy = mockFetch(jsonResponse({ id: "s1" }));
    const file = new File(["data"], "doc.pdf", { type: "application/pdf" });

    // Act
    await api.uploadSource("p1", { file });

    // Assert
    expect(lastHeaders(spy).has("Content-Type")).toBe(false);
  });

  it("returns undefined for a 204 rather than parsing an empty body", async () => {
    // Arrange -- an empty body would throw if handed to res.json()
    mockFetch(new Response(null, { status: 204 }));

    // Act
    const result = await api.listGenerations("p1");

    // Assert
    expect(result).toBeUndefined();
  });
});

describe("artifact download (T-1.5)", () => {
  it("returns bytes, not a URL", async () => {
    // Arrange
    const spy = mockFetch(
      new Response("PPTX", {
        status: 200,
        headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.presentationml.presentation" },
      }),
    );

    // Act
    const blob = await api.downloadGeneration("g1", "pptx");

    // Assert -- jsdom's Blob has no .text(), so assert the payload by size
    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBe("PPTX".length);
    expect(spy.mock.calls[0][0]).toContain("/generations/g1/download?format=pptx");
  });

  it("carries the bearer token, since navigation cannot", async () => {
    // Arrange -- this is precisely why window.open() could not be used
    setToken("tok-abc");
    const spy = mockFetch(new Response("PDF", { status: 200 }));

    // Act
    await api.downloadGeneration("g1", "pdf");

    // Assert
    expect(lastHeaders(spy).get("Authorization")).toBe("Bearer tok-abc");
  });

  it("does not ask for JSON", async () => {
    // Arrange
    const spy = mockFetch(new Response("PPTX", { status: 200 }));

    // Act
    await api.downloadGeneration("g1", "pptx");

    // Assert
    expect(lastHeaders(spy).get("Accept")).not.toBe("application/json");
  });

  it("raises an ApiError instead of returning an error page as a blob", async () => {
    // Arrange
    mockFetch(jsonResponse({ error: { code: "not_found", message: "No pptx artifact." } }, 404));

    // Act / Assert
    await expect(api.downloadGeneration("g1", "pptx")).rejects.toMatchObject({
      status: 404,
      code: "not_found",
    });
  });
});
