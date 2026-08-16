import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: "line",
  use: {
    baseURL: process.env.TIA_E2E_BASE_URL || "http://127.0.0.1:3000",
    headless: true,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
});
