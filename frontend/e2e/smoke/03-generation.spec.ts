import { expect, test } from "@playwright/test";

import { createProject, waitForGenerationTerminal } from "../fixtures";

/**
 * Generate a deck and download it.
 *
 * The download half is the T-1.5 regression guard at the only level that could have
 * caught it: presigning against `http://minio:9000` produced a URL that resolved fine
 * inside Docker and not at all in a browser. Unit tests pass either way.
 */
test.describe("generation", () => {
  test("a Studio deck reaches ready and downloads", async ({ page }) => {
    const projectId = await createProject(page, `E2E Deck ${Date.now()}`);

    const created = await page.request.post(`/api/v1/projects/${projectId}/generations`, {
      data: {
        content_source: "custom",
        custom_markdown: "## Findings\n\nRevenue grew 12% year over year.",
        tone: "professional",
        density: "standard",
        n_slides: 5,
      },
    });
    expect(created.status()).toBe(202);
    const generationId = (await created.json()).id;

    const status = await waitForGenerationTerminal(page, generationId);
    expect(status).toBe("ready");

    const download = await page.request.get(
      `/api/v1/generations/${generationId}/download?format=pptx`,
    );
    expect(download.status()).toBe(200);
    expect(download.headers()["content-disposition"]).toContain("attachment");
    expect((await download.body()).byteLength).toBeGreaterThan(0);
  });

  test("a Studio deck is counted in usage (T-2.2)", async ({ page }) => {
    // The freeform path emitted no usage record, so /usage reported zero for the
    // path users actually use.
    const before = (await (await page.request.get("/api/v1/usage")).json()).tenant
      .generations;

    const projectId = await createProject(page, `E2E Metering ${Date.now()}`);
    const created = await page.request.post(`/api/v1/projects/${projectId}/generations`, {
      data: {
        content_source: "custom",
        custom_markdown: "## Metering\n\nOne deck.",
        tone: "professional",
        density: "standard",
        n_slides: 3,
      },
    });
    expect(created.status()).toBe(202);

    await expect
      .poll(
        async () =>
          (await (await page.request.get("/api/v1/usage")).json()).tenant.generations,
        { timeout: 30_000 },
      )
      .toBeGreaterThan(before);
  });
});
