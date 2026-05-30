# am-identity

Unified identity service for AM Platform.

## Local run

From repo root (`am-platform/`):

```bash
npm run identity:dev
```

Or from this folder:

```bash
npm run dev
```

Loads `.env` / `.secrets.env` from platform root and sets `PYTHONPATH` for shared libraries.

## Main route groups

- `/auth/*` public auth entrypoints (register, login, refresh, logout)
- `/users/me*` authenticated user profile/settings endpoints
- `/internal/*` service-only endpoints

## Postman

Import the collection and environment from [`postman/`](postman/README.md):

- `postman/AM-Identity.postman_collection.json`
- `postman/AM-Identity.local.postman_environment.json`

<!-- dummy trigger commit -->
