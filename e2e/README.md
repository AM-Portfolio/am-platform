# AM Platform E2E (Playwright)

Single home for **API** and **web UI** tests across environments.

## Layout

```
e2e/
  environments/     # local | preprod | dev | prod URLs
  api/              # HTTP tests (identity, subscription, …)
  ui/               # Browser tests (am.asrax.in, Flutter web)
  lib/              # env loader, shared helpers
  tools/            # google-id-token.html for manual token capture
```

## Commands

From `am-platform/`:

```bash
npm install -w @am-platform/e2e
npm run e2e:install -w @am-platform/e2e    # Playwright Chromium

npm run e2e:local:api                        # API vs localhost:8113
npm run e2e:preprod:api                      # API vs am.asrax.in/identity
npm run e2e:preprod:ui                       # Web smoke vs am.asrax.in
```

Set `E2E_ENV=local|preprod|dev|prod` to pick `environments/*.json`.

## Google login API test

1. `python -m http.server 9000` in `e2e/tools/` → sign in at http://localhost:9000/google-id-token.html
2. `$env:GOOGLE_ID_TOKEN="<paste>"`
3. `npm run e2e:preprod:api`

Without `GOOGLE_ID_TOKEN`, the google-token spec is skipped; health + invalid-token tests still run.

## Secrets

Never commit tokens. Optional overrides via env vars (not stored in JSON):

- `GOOGLE_ID_TOKEN` — Google JWT for `/auth/google/token` tests
- `E2E_ENV` — environment name (default `local`)

Service URLs live in `environments/*.json` (same shape as Postman platform envs).
