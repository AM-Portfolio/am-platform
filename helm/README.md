# AM Platform — Helm & Docker

Platform services (`am-identity`, `am-subscription`, `am-notification`) follow the same pattern as [am-market-data](https://github.com/AM-Portfolio/am-market/tree/main/am-market-data):

- **Docker**: one image per service; build context is the `am-platform` repo root (`build_context: ..`).
- **Helm**: flat `values*.yaml` + `vault-mappings.yaml` per service — no local `Chart.yaml`; CI merges these into `AM-Portfolio/am-pipelines/helm/universal-chart`.
- **CI/CD**: publish workflows call `central-build-publish.yml`; manual deploy workflows call `central-deploy.yml`.

## Layout

| Service | K8s / Docker port | Local dev port (`npm run platform:dev`) | Dockerfile | Helm |
|---------|-------------------|----------------------------------------|------------|------|
| am-identity | **8080** | 8113 | `am-identity/Dockerfile` | `am-identity/helm/` |
| am-subscription | **8080** | 8110 | `am-subscription/Dockerfile` | `am-subscription/helm/` |
| am-notification | **8080** | 8111 | `am-notification/Dockerfile` | `am-notification/helm/` |

Local dev sets `APP_PORT` per service in `automation/scripts/platform_env.py` and `run_platform.py`. Docker and Helm always use **8080**, matching other AM services.

Shared libraries (`libraries/am-platform-common`, `libraries/am-platform-security`) and `requirements.txt` are copied into every image.

## Local Docker build

From the `am-platform` root:

```bash
docker build -f am-identity/Dockerfile -t am-identity:local .
docker build -f am-subscription/Dockerfile -t am-subscription:local .
docker build -f am-notification/Dockerfile -t am-notification:local .
```

**CI note:** Service images use public `python:3.12-slim` (not `ghcr.io/am-portfolio/am-python-base`). am-parser in am-market can pull the org base image because that repo has `GHCR_TOKEN` / package access; am-platform avoids the cross-repo 403 by inlining the same runtime (`gcc`, `curl`). Reference: `docker/python-base.Dockerfile`.

## Ingress (dev / prod)

External routes use the `/api` gateway prefix (see `docs/critical_high_gap_resolution.md`). Traefik strip-prefix middleware removes `/api` before traffic hits the service, which exposes routes at `/auth`, `/subscriptions`, `/notifications`, etc.

## Vault

Seed secrets under `apps/data/<env>/services/am-identity`, `am-subscription`, and `am-notification` before first deploy. Infra paths (`postgres`, `mongodb`, `kafka`) reuse existing cluster secrets.

## Workflows

| Workflow | Trigger | Action |
|----------|---------|--------|
| `am-identity.yml` | push/PR on identity + libraries | Build & push `ghcr.io/am-portfolio/am-identity` |
| `deploy-am-identity.yml` | manual | Deploy to preprod/prod |
| Same pattern for subscription and notification | | |

Set `deploy_dev: false` in publish workflows if the dev cluster is not ready yet.
