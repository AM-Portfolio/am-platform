import { test, expect } from "@playwright/test";

test.describe("identity health", () => {
  test("GET /health returns ok", async ({ request }) => {
    const response = await request.get("/health");
    expect(response.ok()).toBeTruthy();

    const body = await response.json();
    expect(body.status).toBe("ok");
    expect(body.service).toBe("am-identity");
  });
});
