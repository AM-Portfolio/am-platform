import { defineConfig } from "@playwright/test";
import { loadE2EEnvironment } from "./lib/env";

const env = loadE2EEnvironment(process.env.E2E_ENV ?? "local");

export default defineConfig({
  testDir: ".",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "api",
      testDir: "./api",
      use: {
        baseURL: env.identityBaseUrl,
        extraHTTPHeaders: {
          Accept: "application/json",
        },
      },
    },
    {
      name: "ui",
      testDir: "./ui",
      use: {
        baseURL: env.webBaseUrl,
        browserName: "chromium",
        viewport: { width: 1280, height: 720 },
      },
    },
  ],
});
