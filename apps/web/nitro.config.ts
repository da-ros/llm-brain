// Nitro build config for the Docker image (TanStack Start compiles through
// nitro; the Lovable wrapper defaults to a Cloudflare worker target, which
// cannot run in a container). Loaded automatically by nitro at build time —
// do NOT import this from vite.config.ts.
export default {
  preset: "node-server",
  routeRules: {
    // The UI calls relative /api/* paths; forward them to the api-router.
    "/api/**": { proxy: "http://api-router:8000/api/**" },
  },
};
