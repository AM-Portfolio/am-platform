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
# ensure PYTHONPATH includes libraries and am-identity
uvicorn am_identity.main:app --reload --port 8113
```

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
