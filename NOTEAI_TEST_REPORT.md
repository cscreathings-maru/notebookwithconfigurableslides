# Presenton / NoteAI Integration - Technical Debugging Report

## Executive Summary
The Presenton editor module is currently returning `404 Page Not Found` for routes like `/editor/template-preview` and failing to load static assets like `404.svg` and `Presenton_Splash.png`. This is caused by a fundamental misalignment between Traefik's reverse-proxy routing rules and Next.js's internal `basePath` logic when deployed using Docker's `standalone` build mode.

---

## 1. What We Have Done

1. **Traefik `stripprefix` adjustment:** We identified that Traefik was stripping the `/editor` prefix before passing requests to Next.js. We temporarily removed this middleware to see if Next.js was expecting the full `/editor/...` path.
2. **Bypassed the "Instance Not Configured" block:** The OpenRouter configuration injection via the browser was failing due to network blocks or missing environment variables in the container. We manually injected the configuration directly into `/app_data/userConfig.json` using a Node script via `docker exec`. This successfully bypassed the configuration error.
3. **Rebuilt the Container:** We triggered a `--build` on the `presenton` docker-compose service to ensure that recently added routes (like `/template-preview` which was added to the repository after the initial image was compiled) were physically present in the `.next` build folder.

Despite these steps, Next.js continues to return a 404 layout (`not-found.tsx`), and the browser console shows 404 errors for static assets like `404.svg`.

---

## 2. Potential Root Causes

The core issue lies in how Next.js handles `basePath` in a Dockerized environment.

### A. Next.js Standalone Build Limitation
The `presenton-custom` Dockerfile builds Next.js using `output: 'standalone'`. In Next.js, when you use standalone mode, the `basePath` **must be configured at build time**. 
However, Presenton's `start.js` script attempts to inject the `basePath: '/editor'` at *runtime* by dynamically modifying `next.config.mjs`. Because the standalone `server.js` does not read `next.config.mjs` at runtime, Next.js operates completely unaware of the `/editor` base path.

### B. The Route Mismatch
Because Next.js has no `basePath` internally:
* When Traefik passes `/editor/template-preview` to the container, Next.js looks for a file at `app/editor/template-preview/page.tsx`.
* This file does not exist (it is located at `app/(presentation-generator)/template-preview/page.tsx`), so Next.js returns the 404 layout.

### C. The Static Asset 404s (`404.svg`, `Presenton_Splash.png`, `/_next`)
Because Next.js is unaware it is hosted under `/editor`, the HTML it renders tells the browser to fetch assets from the root domain.
* The browser requests: `https://notellm.umarsyukri.com/404.svg`
* Traefik checks its rules. The rule for Presenton is `PathPrefix('/editor')`.
* Since `/404.svg` does not start with `/editor`, Traefik routes the request to the main NoteAI frontend container.
* The NoteAI container does not have Presenton's `404.svg` image, so it returns a 404 Network Error.

---

## 3. Recommended Solutions

To achieve a fully working setup where Presenton is hosted flawlessly under `/editor`, the engineering team must implement one of the following architectural fixes:

### Solution 1: Hardcode `basePath` at Build-Time (Recommended)
Since Next.js is running in standalone mode, the `basePath` must be baked into the static assets during the Docker build process.
1. Open `presenton-custom/servers/nextjs/next.config.mjs`.
2. Hardcode the `basePath` directly in the configuration object:
   ```javascript
   const nextConfig = {
     basePath: '/editor',
     output: 'standalone',
     // ...
   }
   ```
3. Rebuild the Presenton container (`docker compose build presenton`).
*Why this works:* Next.js will now natively expect `/editor/...` routes. Furthermore, it will automatically prefix all static assets, so the HTML will correctly request `<img src="/editor/404.svg">`. Traefik will see the `/editor` prefix and route the asset requests to Presenton perfectly.

### Solution 2: Restore `stripprefix` and Expand Traefik Asset Rules
If modifying the Next.js build process is not feasible, you must handle the routing entirely via Traefik.
1. Restore the `stripprefix=/editor` middleware in `docker-compose.lite.yml` so that Next.js receives requests starting from `/`.
2. Expand Traefik's `PathPrefix` rules for the Presenton container to explicitly capture Presenton's static assets from the root.
   ```yaml
   - "traefik.http.routers.presenton.rule=PathPrefix(`/editor`) || PathPrefix(`/_next`) || PathPrefix(`/404.svg`) || PathPrefix(`/Presenton_Splash.png`) /* ... */"
   ```
*Why this works:* Next.js operates as if it is hosted at the root. When it requests root-level assets, Traefik intercepts them and ensures they are delivered to the Presenton container instead of the NoteAI container.

---
*End of Report*
