# Web OTP login (Phase 4f)

Email OTP fallback for web login only. Mobile apps must not call these endpoints.

## Endpoints

- `POST /identity/auth/web/otp/send` — `{ "email": "user@example.com" }`
- `POST /identity/auth/web/otp/verify` — `{ "email", "code" }` → Set-Cookie session

## Policy

- Blocked for mobile User-Agent patterns (403)
- Rate limited per email (429 after threshold)
- Cookie BFF session same as QR completion

## Feature flag

`FeatureFlags.enableWebOtp` in am-modern-ui
