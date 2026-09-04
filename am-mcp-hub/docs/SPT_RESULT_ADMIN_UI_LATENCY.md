# AM MCP Hub — SPT Result (admin UI latency)

Manual SPT-style latency probe of hub admin APIs and HTML shells. User-specific chat/skills/rules stay on the laptop mount only; hub reads locally (no upload to SPT/cloud).

| Field | Value |
|-------|-------|
| Service | `am-mcp-hub` |
| Target | `http://127.0.0.1:8130` |
| Tool | `curl` (5 samples after warm-up) |
| Date | 2026-08-10 (round 2 after chat no-body + single IDE probe) |
| Hub container | `am-mcp-hub-hub-1` (hot-copied modules) |
| Chat index | `~/.asrax/chat-memory/index.sqlite` (~18 MB, 269 conversations, local bind mount) |
| Privacy | Laptop-local vault only; list APIs do not ship `body` off-box |

## Verdict

| Area | Result |
|------|--------|
| Catalog APIs (skills/rules/hooks/agents) | PASS |
| HTML shells | PASS (~10 ms in round 1) |
| Marketplace | PASS |
| Chat list | PASS after fix (was FAIL at ~29 s p50) |

## Round 2 latency (ms) — key endpoints

| Endpoint | Min | p50 | Avg | Max |
|----------|-----|-----|-----|-----|
| chat_list | 184 | **222** | 284 | 556 |
| chat_sources | 21 | **23** | 24 | 26 |
| skills_list | 33 | 75 | 211 | 786 |
| rules_list | 22 | 29 | 165 | 687 |
| marketplace | 113 | 282 | 394 | 1130 |

## Round 3 — Home summary dashboard (2026-08-10)

`GET /api/v1/home-summary` (5 samples after warm-up). Composes catalog counts + marketplace counts + chat sources/recent + google (1.5s timeout). Response omits marketplace `items` and chat `body`. Privacy: `laptop-local`.

| Endpoint | Status | Min | p50 | Avg | Max |
|----------|--------|-----|-----|-----|-----|
| home_summary | 200 | 1189 | 1811 | 1695 | 2095 |

Live payload check: skills=21, chat_total=269, `marketplace.items` absent.

## Round 4 — Catalog/Home/API polish (2026-08-10)

Shell consistency (white hub-page head/foot on Catalog/Tools/Google/Admin), denser library, chat `limit=50` + `offset` + list TTL (~15s), `include_sources` on first page only, Home Sync destinations + History `?source=`, OpenAPI named models/examples.

Measured after hot-copy into `am-mcp-hub-hub-1` (5 samples each):

| Endpoint | Status | Min | p50 | Avg | Max |
|----------|--------|-----|-----|-----|-----|
| chat_list `limit=50&offset=0&include_sources=1` | 200 | 182 | **248** | 484 | 1475 |
| chat_list `limit=50&offset=50&include_sources=0` | 200 | 61 | **75** | 235 | 787 |
| home_summary | 200 | 643 | **813** | 976 | 1746 |
| page_catalog / tools / admin / agents / home | 200 | 32–43 | 49–58 | — | ≤166 |

OpenAPI: home-summary uses `HomeSummaryResponse`; chat/list documents `limit`, `offset`, `include_sources`.

## Round 1 baseline (ms) — before chat no-body fix

| Endpoint | Status | Samples | Min | p50 | Avg | Max |
|----------|--------|---------|-----|-----|-----|-----|
| skills_list | 200 | 5 | 38 | 145 | 382 | 1389 |
| skills_detail | 200 | 5 | 30 | 44 | 50 | 85 |
| rules_list | 200 | 5 | 80 | 106 | 245 | 806 |
| hooks_list | 200 | 5 | 44 | 136 | 334 | 1308 |
| agents_list | 200 | 5 | 35 | 38 | 100 | 327 |
| chat_list | 200 | 5 | 12743 | 28947 | 26951 | 42659 |
| chat_sources | 200 | 5 | 879 | 1669 | 1572 | 1870 |
| marketplace | 200 | 5 | 237 | 412 | 849 | 2777 |
| inspect_report | 200 | 5 | 156 | 188 | 247 | 354 |
| ui_config | 200 | 5 | 6 | 7 | 7 | 7 |
| page_skills | 200 | 5 | 9 | 9 | 9 | 10 |
| page_rules | 200 | 5 | 9 | 10 | 10 | 13 |
| page_history | 200 | 5 | 9 | 12 | 14 | 26 |
| page_marketplace | 200 | 5 | 9 | 11 | 18 | 51 |

## What changed in round 2

- Chat list no longer `SELECT`s `body`; preview uses `title` (or FTS `snippet` when searching). Full transcript stays on laptop until detail open.
- Chat sources cached ~30s in-process.
- Marketplace uses one host `/ide-servers` call (servers + targets), no second round-trip.

## Endpoint map

| Name | URL |
|------|-----|
| skills_list | `/api/v1/asrax/skills` |
| skills_detail | `/api/v1/asrax/skills/am-code-review` |
| rules_list | `/api/v1/asrax/rules` |
| hooks_list | `/api/v1/asrax/hooks` |
| agents_list | `/api/v1/asrax/agents` |
| chat_list | `/api/v1/asrax/chat/list?limit=50&offset=0&include_sources=1` |
| chat_list_more | `/api/v1/asrax/chat/list?limit=50&offset=50&include_sources=0` |
| home_summary | `/api/v1/home-summary` |
| chat_sources | `/api/v1/asrax/chat/sources` |
| marketplace | `/api/v1/marketplace` |
| inspect_report | `/api/v1/inspect-report` |
| ui_config | `/api/v1/ui-config` |
| page_* | `/skills/`, `/rules/`, `/history/`, `/marketplace/` |
