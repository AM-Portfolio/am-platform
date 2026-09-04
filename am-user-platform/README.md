# AM User Platform Service

FastAPI modular monolith for user-facing app state.

| | |
|--|--|
| **Local port** | **8115** |
| **Cluster port** | **8080** (container) |
| **v1 module** | `ai` — sessions, messages, feedback |

## Run locally

```powershell
cd am-platform
npm run user-platform:dev
```

Or:

```powershell
cd am-platform/am-user-platform
pip install -e ../libraries/am-platform-common
pip install -e ../libraries/am-platform-security
pip install -e .
uvicorn am_user_platform.main:app --reload --port 8115
```

Requires PostgreSQL database **`user_platform`** (schema **`ai`**).

### Local Postgres setup

1. Create database and user (once):

```sql
CREATE USER am_user_platform_user WITH PASSWORD 'your_password';
CREATE DATABASE user_platform OWNER am_user_platform_user;
GRANT ALL PRIVILEGES ON DATABASE user_platform TO am_user_platform_user;
```

2. Add to `am-platform/.secrets.env`:

```env
AM_USER_PLATFORM_DB_NAME=user_platform
AM_USER_PLATFORM_DB_USER=am_user_platform_user
AM_USER_PLATFORM_DB_PASSWORD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

3. Migration (or rely on startup `init_db()`):

```powershell
cd am-platform/am-user-platform
python -m am_user_platform.modules.ai.migrations.versions.001_initial_ai_schema
```

## Env vars (main)

| Env | Purpose |
|-----|---------|
| `APP_PORT` | Local default **8115**; cluster **8080** |
| `AM_USER_PLATFORM_DB_*` | Postgres name / user / password |
| `AM_USER_PLATFORM_POSTGRES_HOST` | Laptop override when `POSTGRES_HOST` is cluster DNS |
| `OIDC_JWKS_URL` / `OIDC_ISSUER` | JWT validation (Vault in cluster) |
| `SERVICE_TOKEN` | Optional; primary auth is Keycloak service JWT |

## API summary

| Prefix | Auth | Purpose |
|--------|------|---------|
| `GET /health`, `/health/live`, `/ready` | none | Probes |
| `/internal/ai/*` | Service Bearer | Agents append / context / purge |
| `/v1/user-platform/ai/*` | User JWT | Sessions + feedback |

## Postman

Import `postman/AM-User-Platform.postman_collection.json` + local environment.  
See [`postman/README.md`](postman/README.md).

## Docker build (from am-platform root)

```powershell
cd am-platform
docker build -f am-user-platform/Dockerfile -t am-user-platform:local .
```

## Deploy with amctl

Yes — same pattern as `am-subscription` / `am-notification`. From the service directory:

```powershell
cd am-platform/am-user-platform

# Dry-run first
am deploy --env dev --dry-run

# Laptop Helm (needs kubeconfig + Vault paths populated)
am deploy --env dev --via helm

# Default path: build/push + GitHub Actions Helm (after merge / workflow live)
am deploy --env dev
```

**Before first cluster deploy:**

1. Create Vault path `apps/data/{env}/services/am-user-platform` with DB + OAuth keys  
2. Provision Postgres DB `user_platform` (and keys under infra postgres secret)  
3. Push/merge so `.github/workflows/am-user-platform.yml` exists on the remote repo  

`.am.yaml` sets `context: ..` so local Docker builds use the am-platform monorepo root (libraries + service).

## Docs

- [`docs/AI_USER_PLATFORM_FOLDER_STRUCTURE.md`](../../docs/AI_USER_PLATFORM_FOLDER_STRUCTURE.md)
- [`docs/AI_CHAT_PLATFORM_PLAN.md`](../../docs/AI_CHAT_PLATFORM_PLAN.md)
