# AM Platform — Keycloak Realm Reference Guide

> **Realm:** `am-realm` | **Auth Server:** `http://auth.munish.org/auth`
> 
> This document is the single source of truth for the `am-realm` Keycloak configuration.  
> All resources were provisioned by Terraform — do not edit them manually in the Keycloak UI.

---

## Table of Contents
1. [OIDC Endpoints](#1-oidc-endpoints)
2. [Realm Configuration](#2-realm-configuration)
3. [Roles](#3-roles)
4. [Clients](#4-clients)
   - [Public Clients (Browser & Mobile)](#41-public-clients--browser--mobile)
   - [Confidential Service Clients](#42-confidential-service-clients)
5. [JWT Token Structure](#5-jwt-token-structure)
6. [How Each Service Uses Auth](#6-how-each-service-uses-auth)
7. [User Lifecycle](#7-user-lifecycle)
8. [Credentials & Secrets Management](#8-credentials--secrets-management)

---

## 1. OIDC Endpoints

| Endpoint | URL |
|---|---|
| **Discovery (JWKS, token, etc.)** | `http://auth.munish.org/auth/realms/am-realm/.well-known/openid-configuration` |
| **Issuer** | `http://auth.munish.org/auth/realms/am-realm` |
| **JWKS (public keys)** | `http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/certs` |
| **Token** | `http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/token` |
| **Authorize** | `http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/auth` |
| **Logout** | `http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/logout` |
| **Admin Console** | `http://auth.munish.org/auth/admin/master/console/` |

---

## 2. Realm Configuration

| Setting | Value | Why |
|---|---|---|
| **Realm Name** | `am-realm` | Isolated from Keycloak master realm |
| **Display Name** | AM Ecosystem Realm | Human-readable label |
| **Registration** | ✅ Enabled | Users can self-register |
| **Login with Email** | ✅ Enabled | Email used as username |
| **Duplicate Emails** | ❌ Disabled | One account per email |
| **Verify Email** | Enabled (preprod/prod with Zoho SMTP) | Register triggers VERIFY_EMAIL via Keycloak |
| **Access Token TTL** | 5 minutes | Short for security |
| **SSO Session Idle** | 30 minutes | Extends on activity |
| **SSO Session Max** | 10 hours | Hard cap per day |
| **Password Policy** | min 8 + upper + lower + digit | Enforced at registration & reset |
| **Brute Force** | 10 failures → 15 min lockout | Auto-unlocks after 12h |

---

## 3. Roles

> [!IMPORTANT]
> **Roles describe what a user can DO — not what device or platform they use.**
> Platform information is captured as a `platform` JWT claim, not as a role.

### Realm Roles

| Role | Who Gets It | What It Means |
|---|---|---|
| `user` | **Every new user (default)** | Can log in to all AM apps, view own data |
| `viewer` | Assigned manually | Read-only access across AM apps — no mutations |
| `admin` | Assigned manually | Can manage users and roles via `am-identity` `/admin/*` |
| `super_admin` | Bootstrap once, then assign only by `super_admin` | Break-glass enterprise owner; only role that may grant/revoke `super_admin` |
| `service` | Service accounts only | Internal machine-to-machine — **never assign to humans** |

### Default Role Assignment

```
New user registers / is created
        │
        └─► Auto-assigned: user role
              │
              ├── Can log in to all AM portals immediately
              └── Cannot manage realms, other users, or service endpoints
```

### Promoting a User

To give a user `admin` or `viewer`, go to:
> Keycloak Admin → realm → Users → `{user}` → Role Mappings → Realm Roles → Assign

Or via the `am-identity` API (`PUT` / `POST` / `DELETE` `/admin/users/{id}/roles`) — requires a JWT with `admin` or `super_admin`.

### Realm email (Zoho SMTP)

Keycloak sends verify / reset / required-action mail via Zoho:

| Setting | Preprod value |
|---------|----------------|
| Host | `smtppro.zoho.in` |
| Port | `465` (SSL) |
| From | `noreply@asrax.in` (`Asrax Accounts`) |

Configured by Terraform `smtp_server` on the realm from `KEYCLOAK_SMTP_*` / `terraform.preprod.tfvars`. Apply with `automation/terraform/keycloak/deploy.ps1 -Env preprod`.

---

## 4. Clients

### 4.1 Public Clients — Browser & Mobile

> **No client secret.** Use **Authorization Code Flow + PKCE** for all public clients.

#### `am-web-client` — AM Investment Portal (Web)

| Property | Value |
|---|---|
| **Client ID** | `am-web-client` |
| **Type** | PUBLIC |
| **Flow** | Auth Code + PKCE |
| **Platform Claim** | `"platform": "web"` |
| **Redirect URIs** | `http://localhost:9000/*`, `https://am.munish.org/*`, `https://am.asrax.in/*` |
| **CORS Origins** | `localhost:9000`, `am.munish.org`, `am.asrax.in` |

```javascript
// Frontend usage (e.g. Keycloak JS adapter)
const keycloak = new Keycloak({
  url: 'http://auth.munish.org/auth',
  realm: 'am-realm',
  clientId: 'am-web-client'
});
await keycloak.init({ onLoad: 'login-required', pkceMethod: 'S256' });
```

---

#### `am-diagnostic-client` — Diagnostic & Dev UI

| Property | Value |
|---|---|
| **Client ID** | `am-diagnostic-client` |
| **Type** | PUBLIC |
| **Platform Claim** | `"platform": "web"` |
| **Redirect URIs** | `http://localhost:9001/*` |
| **Usage** | Internal developer testing dashboard only |

---

#### `am-android-client` — AM Android App

| Property | Value |
|---|---|
| **Client ID** | `am-android-client` |
| **Type** | PUBLIC |
| **Flow** | Auth Code + PKCE (mandatory for mobile) |
| **Platform Claim** | `"platform": "android"` |
| **Redirect URIs** | `com.am.portfolio://*`, `com.asrax.portfolio://*`, `http://localhost:9000/*` |

```kotlin
// Android AppAuth usage
val serviceConfig = AuthorizationServiceConfiguration(
    Uri.parse("http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/auth"),
    Uri.parse("http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/token")
)
val request = AuthorizationRequest.Builder(
    serviceConfig,
    "am-android-client",
    ResponseTypeValues.CODE,
    Uri.parse("com.am.portfolio://callback")
).setCodeVerifier(CodeVerifier()).build()
```

---

#### `am-ios-client` — AM iOS App

| Property | Value |
|---|---|
| **Client ID** | `am-ios-client` |
| **Type** | PUBLIC |
| **Flow** | Auth Code + PKCE |
| **Platform Claim** | `"platform": "ios"` |
| **Redirect URIs** | `com.am.portfolio://*`, `com.asrax.portfolio://*`, `https://am.munish.org/app/callback` |

```swift
// iOS AppAuth usage
let configuration = OIDServiceConfiguration(
    authorizationEndpoint: URL(string: "http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/auth")!,
    tokenEndpoint: URL(string: "http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/token")!
)
let request = OIDAuthorizationRequest(
    configuration: configuration,
    clientId: "am-ios-client",
    scopes: [OIDScopeOpenID, OIDScopeProfile, "email"],
    redirectURL: URL(string: "com.am.portfolio://callback")!,
    responseType: OIDResponseTypeCode,
    additionalParameters: nil
)
```

---

### 4.2 Confidential Service Clients

> **Client Credentials flow only.** These are machine accounts — never use in mobile or browser apps.
> All service accounts are auto-assigned the `service` realm role.
> Secrets stored in [`.secrets.env`](./../.secrets.env) — **git-ignored**.

| Service | Client ID | Used By | Port |
|---|---|---|---|
| **am-identity-service** | `am-identity-service` | FastAPI BFF (`/auth/login` password grant + service account) | 8113 |
| **am-gateway-client** | `am-gateway-client` | API Gateway / token introspection | 8000 |
| **am-gateway-streaming-service** | `am-gateway-streaming-service` | Gateway streaming services | 8001 |
| **am-mcp-service** | `am-mcp-service` | MCP services | 8120 |
| **am-fin-agent-service** | `am-fin-agent-service` | Financial agent services | 8130 |
| **am-doc-intelligence-service** | `am-doc-intelligence-service` | Document intelligence services | 8140 |
| **am-analysis-service** | `am-analysis-service` | Analytics microservice | 8030 |
| **am-market-service** | `am-market-service` | Market Data microservice | 8020 |
| **am-market-data-service** | `am-market-data-service` | Dedicated market-data module | 8020 |
| **am-market-parser-service** | `am-market-parser-service` | Market parser module | 8021 |
| **am-portfolio-service** | `am-portfolio-service` | Portfolio microservice | 8060 |
| **am-trade-service** | `am-trade-service` | Trade Management microservice | 8040 |
| **am-subscription-service** | `am-subscription-service` | Subscription service | 8110 |
| **am-notification-service** | `am-notification-service` | Notification service | 8111 |

```python
# Python service — get a machine token (Client Credentials)
import httpx

resp = httpx.post(
    "http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/token",
    data={
        "grant_type": "client_credentials",
        "client_id": "am-portfolio-service",
        "client_secret": os.getenv("AM_PORTFOLIO_CLIENT_SECRET"),
    }
)
token = resp.json()["access_token"]
```

---

### 4.3 Google SSO (Identity Provider Broker)

Google Sign-In is configured as a Keycloak Identity Provider and managed by Terraform.

| Setting | Value |
|---|---|
| **Provider Alias** | `google` |
| **Terraform Inputs** | `TF_VAR_google_client_id`, `TF_VAR_google_client_secret` |
| **UI Redirect Domains** | `http://localhost:9000/*`, `https://am.munish.org/*`, `https://am.asrax.in/*`, `https://am-dev.asrax.in/*` |
| **Flow** | Google -> Keycloak broker -> AM token issuance |

For secure onboarding:
- Always validate anti-replay `state` values in callback flows.
- Never hardcode Google OAuth secrets in repository files.
- Keep separate Google OAuth apps/credentials per environment.

---

## 5. JWT Token Structure

Every access token issued by `am-realm` includes these claims:

```json
{
  "iss": "http://auth.munish.org/auth/realms/am-realm",
  "sub": "3f1a2b3c-...uuid...",
  "azp": "am-android-client",
  "email": "user@example.com",
  "email_verified": false,
  "roles": ["user"],
  "platform": "android",
  "exp": 1748454600,
  "iat": 1748454300
}
```

| Claim | Description |
|---|---|
| `iss` | Token issuer — always the realm URL |
| `sub` | User UUID — stable, use as your internal user FK |
| `azp` | Authorized party — which client logged in |
| `roles` | Realm roles — use for authorization checks |
| `platform` | `web` / `android` / `ios` — for analytics & routing |
| `exp` / `iat` | Expiry / issued at — validate these always |

---

## 6. How Each Service Uses Auth

### Frontend / Mobile apps
```
1. User clicks Login
2. App redirects to Keycloak with PKCE code challenge
3. User authenticates at auth.munish.org
4. Keycloak redirects back with auth code
5. App exchanges code for access_token + refresh_token
6. App sends access_token in: Authorization: Bearer <token>
7. Backend validates token via JWKS (no network call after first fetch)
```

### Backend Services (validating user tokens)
```python
# FastAPI dependency — validate incoming user JWT
from fastapi.security import OAuth2PasswordBearer
from jose import jwt

JWKS_URL = "http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/certs"
ISSUER   = "http://auth.munish.org/auth/realms/am-realm"

def require_role(required: str):
    def checker(token: str = Depends(oauth2_scheme)):
        payload = jwt.decode(token, jwks, algorithms=["RS256"], issuer=ISSUER)
        if required not in payload.get("roles", []):
            raise HTTPException(403, "Insufficient role")
        return payload
    return checker

@router.get("/admin/report")
def admin_report(user = Depends(require_role("admin"))):
    ...
```

### Service-to-Service calls
```python
# Service fetches its own token using Client Credentials
# Then calls another service with that token
headers = {"Authorization": f"Bearer {machine_token}"}
resp = httpx.get("http://am-portfolio-service/internal/data", headers=headers)
```

---

## 7. User Lifecycle

```
Register/Create
      │
      ▼
  role = user (auto)
      │
      ├──► Login via am-identity API (`POST /auth/login`) → azp=am-identity-service (direct access, server-only)
      ├──► Login on web → azp=am-web-client, platform=web
      ├──► Login on Android → azp=am-android-client, platform=android
      └──► Login on iOS → azp=am-ios-client, platform=ios
      │
      ├── Admin promotes to viewer → can read all data
      └── Admin promotes to admin  → can manage users/content

Service Account (never human)
      │
      └── role = service → machine-only endpoints
```

---

## 8. Credentials & Secrets Management

| File | Committed? | Purpose |
|---|---|---|
| [`.env.example`](./../.env.example) | ✅ Yes | Template with placeholder values — safe to commit |
| [`.secrets.env`](./../.secrets.env) | ❌ **NO** | Real credentials — local only, git-ignored |
| `automation/terraform/terraform.tfstate` | ❌ **NO** | Contains plaintext secrets — git-ignored |

### Regenerating a Client Secret

If a secret is compromised:
```powershell
# 1. Regenerate in Keycloak Admin UI:
#    am-realm → Clients → {client} → Credentials → Regenerate Secret

# 2. Re-run terraform to sync state:
npm run tf:plan    # Will detect drift
npm run tf:apply   # Syncs state

# 3. Update .secrets.env with new value
# 4. Redeploy affected services
```

### Sharing Secrets with Team

> [!CAUTION]
> **Never share secrets via Slack, email, or commit them.**
> Use a secrets manager:
> - **1Password** (Teams): Create a vault `AM-Platform-Secrets`
> - **HashiCorp Vault**: Mount at `/secret/am-platform/`
> - **Kubernetes Secrets**: Create sealed secrets in `identity` namespace

---

*Generated by Terraform on 2026-05-28 | Managed by: `am-platform/automation/terraform/`*
