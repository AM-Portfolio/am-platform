# AM Platform — npm scripts (workspace layout)

Run from **`am-platform/`** (root). Each module has its own `package.json`; root only orchestrates.

```bash
npm run help
```

## Workspace map

| Workspace | Path | Package name |
|-----------|------|----------------|
| Automation | `automation/` | `@am-platform/automation` |
| Identity | `am-identity/` | `@am-platform/identity` |
| Common lib | `libraries/am-platform-common/` | `@am-platform/common` |
| Security lib | `libraries/am-platform-security/` | `@am-platform/security` |

Work inside one module:

```bash
cd am-identity
npm run dev
```

Or from root:

```bash
npm run identity:dev
```

## Runtime logs

Every workspace script (except `help`) writes logs under **`logs/<scope>/`** via `run-with-logs.js`:

```text
logs/
├── platform/
├── identity/
├── automation/
├── common/
└── security/
```

Console output is still shown; a copy is saved as `YYYY-MM-DD_HH-mm-ss_<script-name>.log`.

| Script | Action |
|--------|--------|
| `logs:clean` | Delete log files (keeps `logs/README.md`) |

`logs/*` is git-ignored — never commit runtime logs.

## Root orchestration

| Script | Description |
|--------|-------------|
| `help` | List root + all workspace scripts |
| `dev:env:check` | Verify `.secrets.env` has required keys |
| `test` | `npm test` in every workspace that defines `test` |
| `lint` | Lint all workspaces |
| `format` | Format all workspaces |
| `build:compile` / `build:all` / `ci` | Compile + lint + test |

## Root delegates — Identity

| Root script | Runs |
|-------------|------|
| `identity:dev` | `@am-platform/identity` → `dev` (uvicorn :8113) |
| `identity:dev:prod` | no reload |
| `identity:lint` / `identity:compile` | scoped to am-identity |

Aliases: `run:identity`, `dev:identity`

## Root delegates — Libraries

| Root script | Workspace |
|-------------|-----------|
| `common:test` / `common:lint` | `@am-platform/common` |
| `security:test` / `security:lint` | `@am-platform/security` |

Aliases: `test:common`, `test:security`

## Root delegates — Infrastructure

| Root script | Workspace command |
|-------------|-------------------|
| `infra:tf:init` … `infra:tf:output` | `automation` Terraform |
| `infra:keycloak:deploy` | Helm deploy |
| `infra:compose:up` / `down` / `logs` | Local Keycloak Docker |

Aliases: `tf:apply`, `deploy:keycloak`

## Adding a new service

1. Create `services/am-<name>/package.json` with `name: "@am-platform/<name>"` and `dev` / `test` / `lint` scripts.
2. Add path to root `workspaces` array.
3. Add root alias: `"<name>:dev": "npm run dev -w @am-platform/<name>"`.
