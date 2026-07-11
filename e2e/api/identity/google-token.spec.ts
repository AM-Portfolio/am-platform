import { test, expect } from "@playwright/test";
import { googleIdTokenFromEnv } from "../../lib/env";

test.describe("google id_token login", () => {
  test("POST /auth/google/token issues tokens and /users/me works", async ({
    request,
  }) => {
    const idToken = googleIdTokenFromEnv();
    test.skip(!idToken, "Set GOOGLE_ID_TOKEN (see e2e/tools/google-id-token.html)");

    const login = await request.post("/auth/google/token", {
      data: { id_token: idToken },
    });
    expect(login.ok(), await login.text()).toBeTruthy();

    const tokens = await login.json();
    expect(tokens.access_token).toBeTruthy();
    expect(tokens.token_type).toBe("Bearer");

    const profile = await request.get("/users/me", {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    expect(profile.ok(), await profile.text()).toBeTruthy();

    const user = await profile.json();
    expect(user.email).toBeTruthy();
  });

  test("POST /auth/google/token rejects invalid token", async ({ request }) => {
    const response = await request.post("/auth/google/token", {
      data: { id_token: "not-a-valid-jwt" },
    });
    expect(response.status()).toBe(401);
  });
});
