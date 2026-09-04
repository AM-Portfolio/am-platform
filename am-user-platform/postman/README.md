# AM User Platform — Postman (Browser)

Use **Postman on the web** (no desktop install).

## Select environment (required)

Top-right dropdown must **not** say "No environment".

| Environment | When |
|-------------|------|
| **AM User Platform — Prod Public (Browser)** | Browser Postman (recommended) |
| **AM User Platform — Prod Port-Forward** | Laptop + `kubectl port-forward` only |

Your `invalid_client` error was from **No environment** (empty `client_secret`) or the wrong Keycloak client secret.

## Browser run order

1. Select **Prod Public (Browser)**
2. **00 Auth** → Password Login (am-identity) → expect 200
3. **00 Auth** → Client Credentials (am-gateway-client) → expect 200  
   *(optional)* Client Credentials (am-fin-agent-service) — also filled now
4. **02 User Sessions (public)** — list / create / get / rename / delete
5. **03 Gateway Sessions** — same via `https://am.asrax.in/ai` (Flutter path)
6. **04 Feedback**

Skip **01 Health + Internal** in the browser — those need `127.0.0.1:8115`, which cloud Postman cannot reach.

## Auth cheat sheet

| Route | Token |
|-------|-------|
| `/v1/user-platform/ai/*` | User JWT from identity login |
| `/ai/v1/ai/sessions*` | Same user JWT via gateway |
| `/internal/ai/*` | Service JWT (port-forward only) |

## Links

- Collection: **AM User Platform Service** (updated)
- Browser env UID: see `postman/_postman_ids.json`
