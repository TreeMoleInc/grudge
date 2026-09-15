import { defineConfig } from "@playwright/test";

// Runs against the REAL stack (uvicorn + worker + WSL2-hosted Postgres + this
// Vite dev server) - per the Phase 4 plan, this is deliberate: the backend's
// own WS endpoints have zero automated coverage today, so this is the first
// thing that exercises them for real at all. Playwright does NOT start the
// backend/worker itself (they're separate Python processes, not a single
// `npm` command) - start them manually first (see frontend/README.md), same
// as this session's own manual verification did.
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false, // tests share one backend/DB, avoid cross-test interference
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
  },
});
