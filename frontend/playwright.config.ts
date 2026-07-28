import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke journeys against a LIVE stack (T-2.6).
 *
 * These replace `automation/verify_noteai_revamp.py`, which asserted that source files
 * matched regex patterns. It reported "100% pass across 26 criteria" while /editor
 * 404'd, downloads failed, branding was unwired and RAG leaked across projects — it
 * executed no application code, started no server and issued no request.
 *
 * Every test here drives a real browser against a running deployment. Start the stack
 * first (`docker compose -f deploy/docker-compose.lite.yml up -d`) and point
 * E2E_BASE_URL at it; there is deliberately no `webServer` block, because a smoke
 * suite that boots its own private server is not testing the deployment.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8099",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
