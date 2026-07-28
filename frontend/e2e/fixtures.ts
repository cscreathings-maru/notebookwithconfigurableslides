import { expect, type Page } from "@playwright/test";

/** Console errors collected for a page, so a spec can assert the browser stayed clean. */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}

/** Responses that came back 4xx/5xx, so a spec can assert no asset 404s. */
export function collectFailedRequests(page: Page): string[] {
  const failures: string[] = [];
  page.on("response", (res) => {
    if (res.status() >= 400) failures.push(`${res.status()} ${res.url()}`);
  });
  page.on("requestfailed", (req) => failures.push(`FAILED ${req.url()}`));
  return failures;
}

/** Create a project and return its id, read from the URL after navigation. */
export async function createProject(page: Page, name: string): Promise<string> {
  await page.goto("/projects");
  await page.getByRole("button", { name: /new project|proyek baru/i }).click();
  await page.getByRole("textbox").first().fill(name);
  await page.getByRole("button", { name: /create|buat/i }).click();

  await page.getByText(name).first().click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}/);
  return page.url().split("/projects/")[1].split(/[?#]/)[0];
}

/** Poll a project's sources until one reaches ready, or fail with what it did reach. */
export async function waitForSourceReady(page: Page, projectId: string): Promise<void> {
  await expect
    .poll(
      async () => {
        const res = await page.request.get(`/api/v1/projects/${projectId}/sources`);
        if (!res.ok()) return `http_${res.status()}`;
        const sources = (await res.json()) as Array<{ status: string }>;
        return sources[0]?.status ?? "none";
      },
      { timeout: 180_000, intervals: [2_000] },
    )
    .toBe("ready");
}

/** Poll a generation until it leaves the queued/running states. */
export async function waitForGenerationTerminal(
  page: Page,
  generationId: string,
): Promise<string> {
  let final = "unknown";
  await expect
    .poll(
      async () => {
        const res = await page.request.get(`/api/v1/generations/${generationId}`);
        if (!res.ok()) return "queued";
        final = ((await res.json()) as { status: string }).status;
        return final;
      },
      { timeout: 300_000, intervals: [3_000] },
    )
    .not.toMatch(/queued|running/);
  return final;
}
