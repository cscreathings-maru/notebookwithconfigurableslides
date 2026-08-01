import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// The session token lives in localStorage. jsdom's implementation is not reliably
// present under this config, so install a real one when it is missing rather than
// mocking `session.ts` -- the token round-trip is part of what these tests check.
if (typeof window !== "undefined" && typeof window.localStorage?.removeItem !== "function") {
  const store = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: (i: number) => [...store.keys()][i] ?? null,
      get length() {
        return store.size;
      },
    },
  });
}

// jsdom implements neither, and both are load-bearing for the authenticated
// download path (T-1.5): artifacts are fetched as blobs and saved via object URLs.
if (typeof URL.createObjectURL === "undefined") {
  Object.defineProperty(URL, "createObjectURL", {
    writable: true,
    value: vi.fn(() => "blob:mock"),
  });
}
if (typeof URL.revokeObjectURL === "undefined") {
  Object.defineProperty(URL, "revokeObjectURL", { writable: true, value: vi.fn() });
}

// jsdom does not implement scrollIntoView. ChatPanel calls it on every message change
// to keep the thread pinned to the latest turn, so without this stub any test that
// renders a chat message throws from inside a passive effect.
if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    writable: true,
    value: vi.fn(),
  });
}
