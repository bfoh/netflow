import { defineConfig } from '@playwright/test';

// End-to-end tests drive the real UI against a running backend (simulated devices only).
// Start both servers first (see README "Run locally"), or set UNDM_E2E_BASE_URL.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  use: {
    baseURL: process.env.UNDM_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'off',
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
});
