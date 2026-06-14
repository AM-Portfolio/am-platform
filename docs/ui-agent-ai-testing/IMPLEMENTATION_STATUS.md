# Implementation Status — UI Agent AI Testing

> Last updated: 2026-06-14  
> Spec: [DESIGN_REVIEW_HYBRID.md](DESIGN_REVIEW_HYBRID.md)

---

## Summary

| Area | Status |
|------|--------|
| Auth E2E (Playwright, fixed steps) | **Done** |
| Rich HTML/JSON reports (`am-ui-test-report/v1`) | **Done** |
| MCP gateway `run_modern_ui_auth_test` | **Done** |
| LiteLLM MCP tool sync from manifest | **Done** |
| Qdrant `ui_patterns` search/upsert/supersede | **Done** |
| Local image embedder (`embedder.py`) | **Done** |
| Design review node (Hybrid) | **Done** |
| Baseline lifecycle seed/compare/promote | **Done** |
| Promote API `POST /api/v1/design/baseline/promote` | **Done** |
| CLI `--baseline-mode` | **Done** |
| Gateway `promote_design_baseline` MCP tool | Planned (P3) |

---

## LangGraph pipeline

| Node | File | Status |
|------|------|--------|
| plan | `app/agent/planner.py` | Done |
| execute | `app/agent/executor.py` | Done |
| assert | `app/agent/assertions.py` | Done |
| **design_review** | `app/agent/design_review.py` | **Done** |
| self_heal | `app/agent/self_healer.py` | Done |
| report | `app/agent/reporter.py` | Done |

Graph: `plan → execute → assert → design_review → report`

---

## Configuration (`.env`)

```env
DESIGN_REVIEW_ENABLED=true
DESIGN_SIMILARITY_PASS=0.92
DESIGN_SIMILARITY_REVIEW=0.78
DESIGN_GATE_STRICT=false
BASELINE_MODE=compare
QDRANT_HOST=localhost
QDRANT_PORT=6333
# CLIP_EMBEDDING_MODEL=   # optional LiteLLM embedding model
```

---

## Quick commands

```powershell
# Seed baselines (first time, Qdrant required)
python scripts/run_auth_test.py --target-file ../am-modern-ui/testing/targets.preprod.json --baseline-mode seed

# Normal compare (default)
npm run test:auth:preprod

# Promote after weekly UI merge
python scripts/run_auth_test.py --target-file ../am-modern-ui/testing/targets.preprod.json --baseline-mode promote

# Manual promote from report
curl -X POST http://localhost:8130/api/v1/design/baseline/promote -H "Content-Type: application/json" -d "{\"testId\":\"YOUR-TEST-ID\"}"
```

---

## Tests

```powershell
cd am-ui-test-agent
python -m pytest tests/ -q
```

Includes: `test_design_status.py`, `test_embedder.py`, `test_design_review_report.py`

---

## Related

- [DESIGN_REVIEW_HYBRID.md](DESIGN_REVIEW_HYBRID.md)
- [OPERATIONS_WEEKLY_UI_RELEASE.md](OPERATIONS_WEEKLY_UI_RELEASE.md)
- [AM_UI_TEST_AGENT_DESIGN.md](AM_UI_TEST_AGENT_DESIGN.md)
