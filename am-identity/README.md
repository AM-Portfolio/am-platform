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

Do **not** import the files in [`postman/`](postman/README.md) into Postman. They are the Identity **source** for the unified collection.

Use `am-platform/postman/AM-Platform.postman_collection.json` (Identity folder). Rebuild with `python postman/build_platform_postman.py` from `am-platform/`.

<!-- dummy trigger commit -->
