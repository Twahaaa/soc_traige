import { resolve } from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end Playwright config for the SOC triage dashboard.
 *
 * Backing services (Redis :6379, Qdrant :6333) must be up before running —
 * `backend/scripts/run_dashboard_e2e.sh` brings them all up together with this
 * suite. We deliberately do NOT auto-start Redis/Qdrant here (they are stateful
 * containers); `run_dashboard_e2e.sh` handles lifecycle.
 *
 * The two app servers are started as `webServer`s:
 *  - FastAPI dashboard on :8000 (port from settings.yaml)
 *  - Next.js dev on :3000
 * The dev server runs against `.env.local` (NEXT_PUBLIC_API_URL=http://localhost:8000).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
  webServer: [
    {
      command: "uv run uvicorn dashboard.main:app --port 8000 --log-level warning",
      cwd: resolve(__dirname, "..", "backend"),
      url: "http://localhost:8000/api/health",
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      cwd: __dirname,
      url: "http://localhost:3000/dashboard",
      reuseExistingServer: true,
      timeout: 90_000,
    },
  ],
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});