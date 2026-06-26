/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output keeps the production Docker image small.
  output: "standalone",
  // Engine URLs/credentials live only in the backend; the browser only ever
  // talks to the orchestrator's public /api surface (same origin via Traefik).
};

export default nextConfig;
