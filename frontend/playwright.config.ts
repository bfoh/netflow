import { defineConfig } from '@playwright/test';

// End-to-end tests drive the real UI against a running backend (simulated devices only).
// Start both servers first (see README "Run locally"), or set UNDM_E2E_BASE_URL.
// Projects: the workflows at 1280×720; the page checks (accessibility, layout) at a
// 1366×768 laptop and a 390×844 phone (D-119).
const CHECKS = /(a11y|layout)\.spec\.ts/;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  use: {
    baseURL: process.env.UNDM_E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'off',
    launchOptions: process.env.PW_CHROMIUM_PATH ? { executablePath: process.env.PW_CHROMIUM_PATH } : {},
  },
  projects: [
    { name: 'workflows', testIgnore: CHECKS, use: { viewport: { width: 1280, height: 720 } } },
    { name: 'laptop', testMatch: CHECKS, use: { viewport: { width: 1366, height: 768 } } },
    { name: 'phone', testMatch: /layout\.spec\.ts/, use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } },
  ],
});
