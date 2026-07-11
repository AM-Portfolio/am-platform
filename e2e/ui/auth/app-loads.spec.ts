import { test, expect } from "@playwright/test";
import { loadE2EEnvironment } from "../../lib/env";

const env = loadE2EEnvironment(process.env.E2E_ENV ?? "local");

test.describe("web app smoke", () => {
  test("home page loads", async ({ page }) => {
    test.skip(
      env.name === "local",
      "Start am-modern-ui web locally or use preprod E2E_ENV",
    );

    const response = await page.goto("/", { waitUntil: "domcontentloaded" });
    expect(response?.ok()).toBeTruthy();
    await expect(page).toHaveTitle(/.+/);
  });
});
