# AM Identity — Postman

## Import

1. Open Postman → **Import**
2. Select both files:
   - `AM-Identity.postman_collection.json`
   - `AM-Identity.local.postman_environment.json`
3. Activate environment **AM Identity — Local**
4. Set `identity_client_secret` in the environment (from `.secrets.env` → `AM_IDENTITY_CLIENT_SECRET`)

## Run locally

```bash
cd am-platform/am-identity

# Against am-realm (default .secrets.env in am-platform/)
npm run dev

# Against preprod Keycloak (am-preprod-realm — same as am.asrax.in)
npm run dev:preprod
```

Service listens on **http://localhost:8113**.

## Test Google id_token login (Flutter flow)

1. Start service: `npm run dev:preprod` (uses `am-env-vault/.../preprod` secrets)
2. Get a Google **id_token** (valid ~1 hour):
   ```bash
   cd am-platform/automation/scripts
   python -m http.server 9000
   ```
   Open http://localhost:9000/google-id-token.html → Sign in with Google → copy token
3. Call the API:
   - **Postman:** `03 Auth — Google SSO` → **Google Token Login (id_token)** (set env `google_id_token`)
   - **PowerShell:** `.\automation\scripts\test-google-token-api.ps1 -IdToken "<token>"`
   - **curl:**
     ```bash
     curl -X POST http://localhost:8113/auth/google/token \
       -H "Content-Type: application/json" \
       -d '{"id_token":"YOUR_GOOGLE_ID_TOKEN"}'
     ```
4. Optional: `04 Users` → **Get My Profile** with saved `access_token`

## Recommended test order

| Step | Request |
|------|---------|
| 1 | `00 Health` → Health Check |
| 2 | `01 Auth — Registration` → Register User |
| 3 | `02 Auth — Login & Session` → Login (Password) |
| 4 | `04 Users` → Get My Profile |
| 5 | `04 Users` → Update My Settings |

### Google SSO

1. `03 Auth — Google SSO` → Get Google Auth URL
2. Open printed `auth_url` in browser
3. After redirect, copy `code` → set env `google_auth_code`
4. `Google Callback` (uses saved `google_state`)

### Internal APIs

1. `99 Keycloak Helpers` → Client Credentials (am-identity-service)
2. `05 Internal` → Issue Service Token / Get Internal User

## Auto-saved variables

After login/refresh/Google callback, the collection test script sets:

- `access_token`
- `refresh_token`
- `google_state` / `google_auth_url`
