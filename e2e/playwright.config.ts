// End-to-end tests for phase 1, phase 2 and phase 3a. They start the real app themselves, with a brand-new
// empty data folder, so it never touches the data of an app you are using.
//
// Stop the app (./run-demo.sh) before running this: the demo TLS server needs
// port 8443 so the demo claims read "localhost:8443", exactly as in the demo file.
import { defineConfig } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(here, "../backend");

// The config file is loaded more than once (main process and workers); only the first load makes the folder.
if (!process.env.E2E_DATA_DIR) {
  process.env.E2E_DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "evidence-lab-e2e-"));
}
// A throwaway password for the throwaway data folder, shared by the test files. It is never written anywhere.
if (!process.env.E2E_PASSWORD) {
  process.env.E2E_PASSWORD = crypto.randomBytes(18).toString("base64url");
}
const appPort = process.env.E2E_APP_PORT ?? "8010";
process.env.E2E_APP_PORT = appPort;
const tlsPort = process.env.E2E_DEMO_TLS_PORT ?? "8443";
process.env.E2E_DEMO_TLS_PORT = tlsPort;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  globalTeardown: "./global-teardown.ts",
  use: {
    baseURL: `http://127.0.0.1:${appPort}`,
    browserName: "chromium",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  webServer: {
    command: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port ${appPort} --log-level warning`,
    cwd: backend,
    url: `http://127.0.0.1:${appPort}/api/session`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      EVIDENCE_LAB_DATA_DIR: process.env.E2E_DATA_DIR,
      EVIDENCE_LAB_DEMO_TLS_PORT: tlsPort,
      // The main run is always demo mode (local processes), so it gives the same result with or without Docker.
      // Isolated mode gets its own short test in phase2.spec.ts, on a second copy of the app.
      EVIDENCE_LAB_MODE: "demo",
    },
  },
});
