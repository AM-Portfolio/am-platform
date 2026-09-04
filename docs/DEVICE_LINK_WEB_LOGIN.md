# Device link web login (Phase 4d)

Web users sign in by scanning a QR code with the logged-in mobile app.

## Flow

1. Web calls `POST /identity/auth/device-link/start` with PKCE `code_challenge`
2. Web displays QR (contains `device_link_id`) and 6-digit confirmation code
3. Mobile scans QR, fetches `GET /identity/auth/device-link/{id}/preview`, approves with biometric
4. Web polls `GET /identity/auth/device-link/{id}/status?code_verifier=` with `credentials: include`
5. On approved, poll response sets `Set-Cookie: am_session` (no JWT in JSON)
6. Web calls `GET /identity/bff/me` for session profile

## Feature flag

`FeatureFlags.enableQrWebLogin` in am-modern-ui (default off until preprod validation)

## E2E runbook

1. Log in on mobile (Android/iOS)
2. Open web login on Chrome; enable QR flag
3. Scan QR from Profile → Scan to log in on web
4. Confirm code matches web display; approve with biometric
5. Web redirects to dashboard without password entry
