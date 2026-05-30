# AM Notification Service

Lean notification orchestration for AM Platform — Kafka consumer, MongoDB dedupe/preferences, Novu adapter.

## Quick start

```bash
# From am-platform/
pip install -r requirements-dev.txt
npm run tf:notification:apply   # Mongo scoped users on shared cluster
npm run deploy:novu             # Novu Helm (external Mongo/Redis)
npm run notification:dev        # http://localhost:8111
```

## Docs

- [plan_notification.md](../docs/plan_notification.md)
- [task.md](../docs/task.md) — Phase 6

## Health

- `GET /health/live`
- `GET /health/ready` — Mongo + Novu API
