import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/services/**", "src/lib/**", "src/components/**"],
      // Marketing pages and layout shells carry little regression risk. Thresholds
      // are set where Phase 1's defects actually lived -- the API client, the URL
      // handling, and the Studio panel -- rather than at a global number that
      // rewards testing whatever is easiest.
      exclude: ["src/**/*.test.{ts,tsx}", "src/lib/i18n/messages/**"],
      // Thresholds are per-module, not global, and deliberately so. `api.ts` is ~100
      // one-line endpoint wrappers that all funnel through the one `request` helper
      // these tests cover; asserting a function-coverage number would mean writing 100
      // tests that assert a URL string. The gate is regression protection where
      // Phase 1's defects actually lived, so it names those modules explicitly.
      // Untested page and marketing components stay visible in the report (~13%
      // overall) rather than being hidden by a narrowed `include`.
      thresholds: {
        "src/services/api.ts": { statements: 60, branches: 60, lines: 60 },
        "src/services/session.ts": { statements: 90, branches: 60, lines: 90 },
        "src/services/uiPrefs.ts": { statements: 90, branches: 60, lines: 90 },
        "src/lib/download.ts": { statements: 90, branches: 60, lines: 90 },
        "src/lib/structuralDiff.ts": { statements: 90, branches: 60, lines: 90 },
        "src/lib/nav.ts": { statements: 90, branches: 60, lines: 90 },
        "src/components/registry/SectionStructureBuilder.tsx": {
          statements: 80, branches: 60, lines: 80,
        },
        "src/components/project/SlideEditorModal.tsx": {
          statements: 80, branches: 60, lines: 80,
        },
        "src/components/project/StudioPanel.tsx": {
          statements: 75, branches: 60, lines: 75,
        },
      },
    },
  },
});
