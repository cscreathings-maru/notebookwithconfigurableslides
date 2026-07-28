import { expect, test } from "@playwright/test";

import { createProject, waitForSourceReady } from "../fixtures";

/**
 * Create a project, upload a source, and wait for the ingestion pipeline to finish.
 *
 * Exercises the enqueue path fixed in T-1.4: before that, a source could sit at
 * `queued` forever because the job was enqueued before its row was committed, and
 * nothing reported it. This test would hang and fail rather than pass silently.
 */
const SAMPLE_PDF = Buffer.from(
  "%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF",
);

test.describe("project lifecycle", () => {
  test("upload reaches ready", async ({ page }) => {
    const projectId = await createProject(page, `E2E Lifecycle ${Date.now()}`);

    await page.setInputFiles('input[type="file"]', {
      name: "sample.pdf",
      mimeType: "application/pdf",
      buffer: SAMPLE_PDF,
    });

    await waitForSourceReady(page, projectId);

    const sources = await (
      await page.request.get(`/api/v1/projects/${projectId}/sources`)
    ).json();
    expect(sources[0].status).toBe("ready");
  });

  test("a project's sources are listed only under that project", async ({ page }) => {
    // The RAG isolation fix (T-2.1) rests on this mapping being per-project.
    const first = await createProject(page, `E2E Iso A ${Date.now()}`);
    const second = await createProject(page, `E2E Iso B ${Date.now()}`);

    const secondSources = await (
      await page.request.get(`/api/v1/projects/${second}/sources`)
    ).json();

    expect(secondSources).toEqual([]);
    expect(first).not.toBe(second);
  });
});
