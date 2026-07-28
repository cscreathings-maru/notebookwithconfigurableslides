/**
 * T-2.5: the session token gates every authenticated call, including the artifact
 * download added in T-1.5. Small module, but everything depends on it.
 */

import { beforeEach, describe, expect, it } from "vitest";

import { clearToken, getToken, setToken } from "@/services/session";
import {
  getNavCollapsed,
  getStoredLocale,
  setNavCollapsed,
  setStoredLocale,
} from "@/services/uiPrefs";

beforeEach(() => {
  window.localStorage.clear();
});

describe("session token", () => {
  it("returns null before a session exists", () => {
    expect(getToken()).toBeNull();
  });

  it("round-trips a token", () => {
    // Act
    setToken("tok-123");

    // Assert
    expect(getToken()).toBe("tok-123");
  });

  it("clears the token on sign-out", () => {
    // Arrange
    setToken("tok-123");

    // Act
    clearToken();

    // Assert
    expect(getToken()).toBeNull();
  });
});

describe("nav collapse preference", () => {
  it("is null when never set, so callers can pick a screen-aware default", () => {
    expect(getNavCollapsed()).toBeNull();
  });

  it("round-trips true", () => {
    setNavCollapsed(true);
    expect(getNavCollapsed()).toBe(true);
  });

  it("round-trips false rather than collapsing it to null", () => {
    // Arrange -- false and "unset" mean different things here
    setNavCollapsed(false);

    // Assert
    expect(getNavCollapsed()).toBe(false);
  });
});

describe("stored locale", () => {
  it("is null when never chosen", () => {
    expect(getStoredLocale()).toBeNull();
  });

  it("round-trips a supported locale", () => {
    setStoredLocale("id");
    expect(getStoredLocale()).toBe("id");
  });

  it("rejects a value that is not a supported locale", () => {
    // Arrange -- a stale or hand-edited localStorage entry
    window.localStorage.setItem("pnl.ui.locale", "fr");

    // Assert -- falls back rather than rendering an unknown catalogue
    expect(getStoredLocale()).toBeNull();
  });
});
