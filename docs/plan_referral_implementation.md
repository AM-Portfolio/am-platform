# AM Referral + New-User Trial — Implementation Plan (v1.1)

**Status:** Ready for implementation (high-confidence design)  
**Plan score (design now):** **9.1 / 10**  
**Plan score (after committed mitigations in this doc):** **9.4 / 10**  
**Ship score (after Phase 1–3 green in staging):** target **9.5 / 10**  
**Reverify:** 2026-09-13 (loopholes locked in §17)  
**Owners:** `am-identity` (capture + lifecycle events) · `am-subscription` (trial + referral ledger + timed Pro) · `am-notification` (notify)  
**Not in scope (v1 core):** `am-user-platform`, Lago **wallet/cash credits**, attaching referral to existing accounts, manual referral code entry after reinstall.  
**In scope later:** Lago **coupons** for paid-plan discounts (§18 / Phase 6) — not a wallet.  

**Companion docs:**

| Doc | Purpose |
|-----|---------|
| [design/referral-system.drawio](./design/referral-system.drawio) | Architecture / sequence / ER / grant diagrams (draw.io) |
| [plan_referral_todo_checks.md](./plan_referral_todo_checks.md) | Pointer only — **full TODO is §20 in this file** |

**Single-file workflow:** read §§1 + 19 for rules → implement from **§20 Coding TODO**.  
**Before coding:** §19 Pre-coding locks (delay runner, social signup, delay UX, code format, share URL).

---

## 0. What changed in v1.1 (from 7.0 plan)

| Topic | v1.0 (score ~7) | v1.1 (score **9.1** design) |
|-------|-----------------|----------------------|
| New user Pro | Only if referred → 14d | **Every** new user → **1 month (30d) Pro trial** |
| Referral reward | Both sides +14d | **Referrer only** → **+14d Pro** per qualify |
| Referee from referral | +14d | Gets the **same 30d trial** as any new user (no extra referral Pro) |
| Timed grant design | Underspecified (W1 critical) | Unified `pro-days` grant with `reason=trial\|referral\|paid` + expiry matrix |
| Score drivers | Open critical gaps | Critical gaps closed in design; remaining = build risk |

---

## 1. Product rules (locked)

| Rule | Decision |
|------|----------|
| Who activates a referral | **New users only** — `referral_code` on **register** only. No attach later. |
| How old users participate | Share invite / download link (`?ref=CODE`). |
| **New-user trial** | **Every** new user, after **email verified**, gets **30 days** `am_pro` free trial (`grant_source=trial`). Independent of referral. |
| **Referral reward** | **1 qualified referral → +14 days** `am_pro` for the **referrer only**. |
| Cap | Referrer max **12** qualified referrals (lifetime). |
| Qualify | Referee **email verified** (same moment trial starts for referee). |
| Device binding | Referral attribution: **one install / device**. Install-scoped `ref` only. |
| Redownload | Reinstall clears `ref` → **referral does not activate**. Trial still applies on new account if they create one (normal signup). |
| Device reuse | Same `device_id` → at most one non-rejected referral attribution (`device_already_used`). |
| Billing | Timed Pro via subscription + Lago plan sync. **No** Lago wallet in v1. |
| **Trial duration** | Exactly **30 × 24 hours** from `email_verified_at` (UTC). Not calendar-month. |
| **Trial delay (anti-farm)** | Configurable `TRIAL_GRANT_DELAY_HOURS` (default **24** in deployed envs, **0** in unit tests). Trial Pro activates at `verified_at + delay`. |
| **Referrer reward delay** | Referrer +14d granted only after delay window passes **and** attribution still valid (default same 24h). Reduces instant farm cash-out. |
| **Paid sticky** | Boolean `is_paid` (or equivalent) is **sticky** while paid active. Expiry worker **never** downgrades paid. |
| **Trial once per email** | Normalized email fingerprint unique for trial grants (blocks delete+re-register same email). |
| **Referral rate limit** | Max **3** referrer rewards per referrer per UTC day (in addition to lifetime cap 12). |
| **No backfill** | Existing accounts already on free/paid do **not** get a one-time trial. Trial is for **new** verified users only. |
| **Email fingerprint** | Normalize: lowercase, trim; strip Gmail `+tag` and dots for `gmail.com`/`googlemail.com` before hash (closes `a+1@` alias farm). |

### Reward matrix (clear)

| Actor | Trigger | Pro grant |
|-------|---------|-----------|
| Any new user (referred or not) | Email verified | **30 days trial** once |
| Referrer | Referee email verified + attribution OK | **+14 days** (stacks, max 12×) |
| Referee | Via referral code | **No extra days** beyond the standard 30d trial |

### User journeys

1. **Referrer** — Invite friends → share `?ref=CODE` → when friend verifies email → referrer gets +14d Pro (if under cap).  
2. **New user (no ref)** — Register → verify email → **30d Pro trial**.  
3. **New user (with ref, first install)** — Register with code + `device_id` → verify email → **30d trial** + referrer gets **14d**.  
4. **Redownload** — No local `ref` → no referral attribution; if they already have an account, login as usual.  
5. **Cap** — 13th qualify for a referrer → `referrer_cap_reached` (referee still gets trial).

---

## 2. Service ownership

```text
am-identity      → register(+referral_code,+device_id), Kafka user_registered + email_verified
am-subscription  → 30d trial grant, referral codes/attributions (max 12), referrer +14d, expiry worker
am-notification  → trial started, referral rewarded
am-user-platform → NOT used
Lago             → plan sync only
```

Aligns with [adr_001_service_boundaries.md](./adrs/adr_001_service_boundaries.md) and [adr_002_database_ownership.md](./adrs/adr_002_database_ownership.md).

### 2.1 Loose coupling (yes — keep it)

**Yes.** This design stays **loosely coupled** if we follow these rules:

| Rule | Do | Don’t |
|------|----|-------|
| Sync boundary | Identity accepts `referral_code` as opaque string only | Identity must not call subscription HTTP on register |
| Async boundary | Kafka events only (`user_registered`, `email_verified`) | Shared DB tables across identity + subscription |
| Commercial truth | Subscription owns codes, attributions, grants, expiry | Notification / identity storing Pro days |
| Notify | Subscription emits `trial_started` / `referral.rewarded`; notification maps events | Subscription importing Novu SDKs deeply (optional thin publish OK) |
| Billing | Subscription → Lago provider interface | Identity talking to Lago |
| Failure isolation | If subscription consumer down, register still succeeds; retry/idempotent consume | Register fails because referral ledger is down |

```text
[App] --HTTP--> [am-identity] --Kafka--> [am-subscription] --HTTP--> [Lago]
                                      |--Kafka--> [am-notification]
```

**Coupling smell to reject in PRs:** identity importing subscription clients; subscription reading Keycloak DB; Flutter calling Lago directly for trial.

**Solve if coupling creeps:** ADR review in PR checklist; contract tests on event payloads only (not service internals).

---

## 3. Architecture summary

See [design/referral-system.drawio](./design/referral-system.drawio).

```text
Register (±ref, device_id)
  → identity creates user
  → Kafka user_registered
      → subscription: attribute pending (if ref valid)

Email verified
  → Kafka email_verified
      → subscription ALWAYS: grant 30d trial (idempotent key trial:{user_id})
      → if pending attribution: qualify → grant referrer +14d → referral.rewarded
```

Reinstall → no `ref` → no attribution; trial still granted on verify for that new signup.

---

## 4. Data model (`am-subscription` Postgres)

### `referral_codes` / `referral_attributions`

Unchanged intent from v1.0 (`device_id`, cap indexes, reject reasons).  
Attribution reward path creates rewards for **referrer only**.

### `referral_rewards`

| Column | Notes |
|--------|--------|
| `attribution_id` | FK (nullable if we ever log non-referral grants elsewhere — prefer keep referral-only here) |
| `beneficiary_user_id` | **Referrer** |
| `reward_type` | `pro_days` |
| `days` | `14` |
| `plan_code` | `am_pro` |
| `idempotency_key` | `ref-reward:{attribution_id}:referrer` |
| `granted_at` / `expires_at` | |

### Subscription grant metadata (unified — closes paid/trial/referral holes)

| Field | Values / notes |
|-------|----------------|
| `is_paid` | **Sticky** while Lago/AM say paid active. Expiry worker skips downgrade if true. |
| `grant_source` | Last *non-paid* grant reason for display: `trial` \| `referral` \| `bootstrap` — **never overwrite** when `is_paid=true` |
| `trial_pro_expires_at` | Set once: `verified_at + TRIAL_GRANT_DELAY_HOURS + 30×24h` |
| `referral_pro_expires_at` | Extended by +14×24h per rewarded referral (after reward delay) |
| `trial_email_fingerprint` | Unique normalized email hash for trial-once-per-email |
| **Effective Pro** | If `is_paid` → Pro. Else if `now < max(trial, referral)` → Pro. Else free. |

### Idempotency keys (required)

| Grant | Key |
|-------|-----|
| New-user trial | `trial:{user_id}` |
| Referrer reward | `ref-reward:{attribution_id}:referrer` |

### Extra tables / indexes (loophole fixes)

| Store | Purpose |
|-------|---------|
| Unique `trial_email_fingerprint` | One trial per email lifetime |
| Unique partial `device_id` on attributions | One referral bind per device |
| `(referrer_user_id, rewarded_on_date)` count ≤ 3 | Daily referrer reward rate limit |
| Grant outbox / retry | Lago sync must eventually succeed |

---

## 5. APIs

### Identity

| Method | Path | Change |
|--------|------|--------|
| POST | `/auth/register` | Optional `referral_code`, `device_id` |

Publish `am.identity.user_registered.v1` and `am.identity.email_verified.v1`.  
No post-signup attach / no reinstall restore.

### Subscription (user JWT)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/subscriptions/referrals/me` | Code, share URLs, `qualified_count`, `remaining` |
| GET | `/subscriptions/referrals/me/history` | Attributions + referrer rewards |
| GET | `/subscriptions/me` | Already exists — must expose trial / referral expiry fields |

### Subscription (internal)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/subscriptions/internal/referrals/attribute` | Pending attribution |
| POST | `/subscriptions/internal/referrals/qualify` | Qualify + referrer +14d |
| POST | `/subscriptions/internal/grants/pro-days` | **Unified** timed Pro (trial 30 / referral 14) |

Example — trial:

```json
{
  "user_id": "kc-sub",
  "days": 30,
  "plan_code": "am_pro",
  "reason": "trial",
  "idempotency_key": "trial:{user_id}"
}
```

Example — referrer reward:

```json
{
  "user_id": "referrer-sub",
  "days": 14,
  "plan_code": "am_pro",
  "reason": "referral",
  "idempotency_key": "ref-reward:{attribution_id}:referrer"
}
```

**Grant algorithm (must not clobber paid):**

1. If `is_paid == true` → **do not** change plan; still may record referral ledger / banked `referral_pro_expires_at` for post-cancel.  
2. Else set `am_pro`, enqueue Lago sync (retryable).  
3. If `reason=trial` → set `trial_pro_expires_at` once; set fingerprint; ignore duplicate key.  
4. If `reason=referral` → `referral_pro_expires_at = max(now, current) + 14×24h` after delay gate.  
5. Audit `actor=system:{reason}`.

**Bootstrap coexistence:** `get_or_create` may create `am_free` / bootstrap first. Trial grant on verify is the **only** path that starts the 30×24h Pro trial. Never grant trial from bootstrap alone.

---

## 6. Kafka events

| Event | Producer | Consumer action |
|-------|----------|-----------------|
| `am.identity.user_registered.v1` | identity | attribute pending (payload: `user_id`, `email`, `referral_code?`, `device_id?`) |
| `am.identity.email_verified.v1` | identity | schedule/apply trial; qualify referral (payload **must repeat** `referral_code?`, `device_id?`, `email`) |
| `am.subscription.trial_started.v1` | subscription | notification |
| `am.referral.qualified.v1` | subscription | notification |
| `am.referral.rewarded.v1` | subscription | notification (referrer) |

**Kafka order loophole fix:** `email_verified` consumer must **upsert** pending attribution from payload if register event was late/missing, then apply trial + qualify. Both paths idempotent.

**Ship gate:** Phase 1 Kafka events must land before Phase 2 consumers go live.

ADR-003 envelope preferred.

---

## 7. Cap, stacking, trial coexistence

- Cap checks at attribute + qualify (row lock on referrer code row).  
- Lifetime max **12** + daily max **3** referrer rewards.  
- Referrer stacking: +14×24h per reward after delay.  
- Referee: **30×24h trial only**.  
- Effective free Pro end = `max(trial_pro_expires_at, referral_pro_expires_at)`.  
- Expiry worker: if `is_paid` → skip; else if now > effective end → revert free + Lago sync.  
- Paid cancel: if banked `referral_pro_expires_at` still in future → remain Pro until that end (`is_paid=false`).

---

## 8. Anti-fraud + loopholes closed (locked)

See full table in **§17**. Summary enforced in v1:

| Control | Rule |
|---------|------|
| Self same user | Reject `self_referral` |
| Self alt-email (soft) | Reject if normalized email equals referrer email from event |
| Device | Required non-empty `device_id` (≥16 chars UUID) for referral attribute; reject `device_already_used` |
| Referrer device reuse | Reject if `device_id` was ever used on an attribution where that user was **referrer or referee** |
| Trial once | Unique `trial_email_fingerprint` |
| Farm speed | `TRIAL_GRANT_DELAY_HOURS` + referrer reward delay (default 24h) |
| Farm volume | Cap 12 + 3/day + metrics/alerts |
| Internal API | Service JWT only; deny user tokens on grant routes |
| Web | Same UUID in localStorage; no nullable skip for referral |

---

## 9. App / marketing + Modern UI (`am-modern-ui`)

### 9.1 Capture / share

- Persist `ref` + generate stable install `device_id` (UUID) install-scoped.  
- Deferred deep link for store installs; track `ref_captured` vs `ref_attributed`.  
- Copy: “New accounts get 1 month Pro free (may start after a short security delay). Invite friends — you get 14 days Pro per friend (max 12, fair-use limits apply).”  
- FAQ: reinstall clears invite; trial once per email.  
- No manual referral code entry after signup/reinstall.

### 9.2 First-run after referral approved (referee)

When the new user’s referral qualifies (or on first app open after verify if attribution exists):

| UI | Behavior |
|----|----------|
| One-time sheet / banner | “You joined with invite **{CODE}**” (and optional referrer display name if exposed) |
| Dismiss | Set `referral_intro_seen=true` (local + optional user prefs) — show **once** |
| Data | From `GET /subscriptions/me` or `GET /subscriptions/referrals/me` → `referral_code_used`, `referrer_code`, status |

### 9.3 Settings → Referral section (referrer + status)

In app **Settings**, add a **Referral** section:

| Field | Source |
|-------|--------|
| Your invite code + share / copy | `GET /subscriptions/referrals/me` |
| Share link | Same |
| Successful invites | `qualified_count` / remaining of 12 |
| History list | `GET /subscriptions/referrals/me/history` (date, status rewarded/pending/rejected) |
| Banked Pro days note | If `is_paid` and referral expiry banked — short explainer |

**Package touchpoints:** `am-modern-ui` / `am_app` settings routes; follow existing settings patterns (`am-flutter-ui` skill when implementing).

---

## 10. Implementation phases

| Phase | Focus | Exit gate |
|-------|--------|-----------|
| 0 | Docs (this + todo + draw.io) | Merged |
| 1 | Identity register fields + **Kafka registered/verified** | Events visible in staging |
| 2 | Referral schema + APIs + cap + device | Attribute/qualify tests green |
| 3 | **Unified pro-days grant** + **30d trial** + referrer 14d + expiry | Paid never downgraded |
| 4 | Notification + **Flutter** first-run + **Settings → Referral** | E2E UI happy path |
| 5 | Hardening, metrics, fraud backlog | Regression matrix green |
| 6 | **Lago coupons** for custom paid-plan offers (optional) | Ops can create/apply coupon per customer |

---

## 11. Key code touchpoints

| Area | Path |
|------|------|
| Register schema | `am-identity/am_identity/schemas/auth.py` |
| Register / verify | `am-identity/am_identity/api/auth_router.py`, Keycloak provider |
| Identity Kafka | `am-identity/am_identity/core/kafka.py` |
| Subscription service | `am-subscription/am_subscription/services/subscription_service.py` |
| Bootstrap / create sub | existing get_or_create — hook trial on verify, not only bootstrap free |
| Lago | `am-subscription/am_subscription/providers/lago_provider.py` |
| Internal routes | `am-subscription/am_subscription/api/internal_router.py` |
| Plans | helm / lago-plans `am_pro` |
| Notification | `am-notification/am_notification/services/event_mapping.py` |
| Flutter settings / first-run | `am-modern-ui` (`am_app` settings + onboarding) |
| Lago coupons (Phase 6) | `lago_provider.py` + internal coupon routes |

---

## 12. Plan score — where we cut the number, how we solve, re-rate

### 12.0 Score waterfall (start at 10 — where points were cut)

This is the explicit cut-the-number math for **design now** (code not shipped yet):

| Step | Delta | Running | Why cut |
|------|------:|--------:|---------|
| Ideal plan | | **10.0** | Perfect product + architecture + already built + fraud-proof + full ops UI |
| - N1 Timed grant / expiry **unbuilt** | -0.40 | 9.60 | Highest eng risk (paid Pro safety) |
| - N2 Trial farm / cost risk | -0.25 | 9.35 | Every verify gets 30d Pro |
| - N3 Kafka events **not shipped** | -0.20 | 9.15 | Pipeline blocked until Phase 1 |
| - N4 Spoofable device_id | -0.10 | 9.05 | Soft device bind |
| - N5 Deep-link ref loss | -0.10 | 8.95 | Store install drop-off |
| - N9 No AM all-users admin UI | -0.10 | 8.85 | Ops on Lago only |
| - N6/N7/N8 (product honesty / non-goals) | -0.05 | **8.80** | Redownload UX, score!=ship, no wallet |
| **Design now** | | **8.8** | |

**Not cut (kept full credit):** product clarity (30d trial + referrer 14d), service ownership / ADR fit, cap=12 rules, loose coupling via Kafka (sec 2.1).

**Earlier cut (v1.0 recovered in v1.1):** ~1.8 points were design holes (both-sides 14d confusion, no grant algorithm, no Kafka gate). Those are **no longer deducted**.

### 12.1 What 8.8 means

| This score is | This score is **not** |
|---------------|------------------------|
| Design / product clarity for v1.1 | Proof the system is already built |
| Confidence we know *what* to build | Fraud-proof or cost-proof |
| Higher than 7.0 because ambiguities were removed | A claim of almost perfect |

### 12.2 Dimension table

| Dimension | v1.0 | Design now | After mitigations | Why |
|-----------|------|------------|-------------------|-----|
| Product clarity | 9 | **10** | **10** | Trial vs referral matrix clear |
| Architecture / coupling | 9 | **9.5** | **9.5** | Kafka-only; sec 2.1 rules |
| Reuse of existing code | 6 | **7** | **8** | Grant built on Lago paths |
| Implementability | 6 | **8** | **9** | Algorithms + playbook |
| Fraud resistance | 6 | **7** | **8** | Metrics + optional delay |
| Operability / admin | 6 | **7.5** | **9** | sec 16 P1-P2 APIs |
| Cap / device | 8 | **9** | **9** | Specified |
| Delivery risk control | — | **9** | **9.5** | Kafka gate enforced |
| **Overall** | **7.0** | **8.8** | **9.3** | See waterfall recoveries |

After mitigations = solutions below are **committed in this plan** (not yet coded).

### 12.3 Negative points + how to solve (recovers the cuts)

| # | Cut | Negative | How to solve (committed) | Points recovered when done |
|---|----:|----------|--------------------------|----------------------------|
| N1 | -0.40 | Timed Pro grant / expiry unbuilt | Unified pro-days; dual expiry; paid short-circuit; expiry worker; paid-preserve tests; 7d staging soak | **+0.35** (leave -0.05 until soak done) |
| N2 | -0.25 | 30d trial farm / cost | Metrics + alert; optional 24h trial delay flag; Lago active-Pro count | **+0.15** (attestation later) |
| N3 | -0.20 | Kafka not shipped | Phase 1 hard gate before consumers | **+0.20** when staging events green |
| N4 | -0.10 | Spoofable device_id | Stable install id v1; Integrity/Attest backlog | **+0.05** in v1 |
| N5 | -0.10 | Deep-link loss | Deferred deep link + ref_captured vs ref_attributed funnel | **+0.05** |
| N6 | -0.02 | Redownload UX | FAQ + support macro (intentional) | **+0.00** (accepted) |
| N7 | -0.02 | Score != ship | DoD = todo matrix, not this number | **+0.00** (process) |
| N8 | -0.01 | No wallet | Explicit non-goal | **+0.00** (accepted) |
| N9 | -0.10 | No AM admin list | sec 16: email on Lago customer; internal get/list by user; optional Hub page P3 | **+0.10** at P2 |

### 12.4 How to solve — actionable playbook

| Neg | Owner | Do this first | Done when |
|-----|-------|---------------|-----------|
| **N1** | am-subscription | POST /internal/grants/pro-days + dual expiry + expiry worker | Paid-preserve tests green; soak |
| **N2** | subscription + ops | Metrics trial_granted, rejects_*; alert | Dashboard live |
| **N3** | am-identity | Kafka user_registered + email_verified | Phase 1 exit gate |
| **N4** | Flutter | Stable install-scoped device_id | Sent on register |
| **N5** | App + marketing | Deferred deep link + funnel metrics | Drop-off visible |
| **N6** | Product | FAQ: reinstall clears invite; trial still for new accounts | Macros ready |
| **N7** | Eng lead | Ship only on todo matrix | Score not ship gate |
| **N8** | Product | No wallet in v1 | Non-goal |
| **N9** | subscription | Internal get-by-user + email on Lago customer | Ops lookup without guessing |
| **Coupling** | all | PR reject sync identity->subscription calls | sec 2.1 checklist |

### 12.5 Re-rate (after solutions committed in plan)

| Score type | Value | Meaning |
|------------|------:|---------|
| Design now (code missing) | **8.8** | Honest today |
| Design after mitigations written + accepted | **9.3** | 8.8 + recovery (capped until code exists) |
| After Phase 1-3 staging green | **~9.5** | N1 soak + N3 done |
| Perfect 10 | **blocked** | Needs attestation (N4) + near-perfect deep links (N5) + long production soak |

**Recovery math:** 8.80 + 0.35 + 0.15 + 0.20 + 0.05 + 0.05 + 0.10 = **9.70** theoretical; we **cap design-after-mitigations at 9.3** until code exists (avoid scoring fiction). Ship target **9.5** after staging proof.

### 12.6 Keep loose coupling while solving

When implementing N1-N9:

1. Identity still **never** calls subscription.
2. Grants only inside subscription.
3. Admin/ops APIs are **subscription internal** (service JWT), not identity.
4. Lago stays behind provider interface.
5. Notification stays event-driven.

---

## 13. Weakest points — counter & reverify

| Metric | Value |
|--------|-------|
| **Open** | **3** (build-only; design loopholes closed in §17) |
| **Critical (design)** | **0** |
| **High (build)** | **1** — W1 grant worker still unbuilt |
| **Medium** | **2** — W5 deep-link residual, W6 reinstall UX |
| **Closed in plan** | W2 farm controls, W3 Kafka gate, W4 cap lock, L1–L15 §17 |
| **Last reverify** | 2026-09-13 (loophole lock pass) |

| ID | Severity | Point | Mitigation | Status |
|----|----------|-------|------------|--------|
| **W1** | High | Timed Pro grant code unbuilt | §4–5 + §17 L5/L6/L9 | Open — **build** |
| **W2** | — | Email farm | Delay + email fingerprint + 3/day + metrics §17 L1/L3/L4 | **Closed in plan** |
| **W3** | — | Identity Kafka | Phase 1 gate | **Closed in plan** |
| **W4** | — | Cap race | Row lock | **Closed in plan** |
| **W5** | Medium | Deep-link residual loss | Deferred link + funnel; some loss accepted | Open (ops) |
| **W6** | Medium | Redownload UX | FAQ intentional | Open (product) |

---

## 14. Acceptance criteria (v1.1 + loophole locks)

- [ ] Trial = **30×24h UTC** from verified_at (+ configured delay)  
- [ ] Trial once per **email fingerprint**; delete+re-register same email → no second trial  
- [ ] New user with valid ref → pending → after delay: trial + referrer +14×24h  
- [ ] Cap 12 lifetime + max 3 referrer rewards / UTC day  
- [ ] Self-referral + same-email + device reuse rejected  
- [ ] `device_id` required (≥16 char UUID) for referral  
- [ ] Kafka out-of-order: email_verified upserts pending then qualifies  
- [ ] `is_paid` sticky; expiry never downgrades paid; banked referral days after cancel  
- [ ] Bootstrap free ≠ trial; trial only on verify path  
- [ ] Lago sync retry/outbox; no manual Lago drift without AM rows  
- [ ] Internal grants: **service JWT only**  
- [ ] Redownload → no referral; FAQ documented  
- [ ] Unit tests cover §17 L1–L15 happy/negative paths  
- [ ] Ops lookup §16 + Lago metadata (§16.5) for test vs prod referrals  
- [x] Flutter: first-run shows invite **CODE** once; Settings → Referral shows count/history (§9) — notification deferred  
- [ ] Draw.io + todo aligned  
- [ ] §19 pre-coding locks implemented (schedules poller, social verify path, delay UX, code format)  
- [ ] (Phase 6) Lago coupons create/apply for custom paid plans (§18)  

---

## 15. Non-goals (keep score honest)

- Cash / Lago **wallet** credits (different from **coupons** in §18)  
- Referee getting +14d *in addition* to trial  
- Referral attach after signup  
- Perfect device attestation (Play Integrity) in v1 — backlog only  
- Full AM billing console rewrite in v1  
- Zero deep-link loss on all stores (impossible to guarantee)  
- Using Lago coupons as a substitute for free trial/referral Pro grants  

---

## 16. Admin panel — how to see users’ plan details

### 16.1 What exists today (use this now)

There is **no** AM MCP Hub / `am-subscription` screen that lists “all users + plan”. The operator UI for billing is **Lago Front**.

| Env | Admin UI |
|-----|----------|
| munish | `https://lago.munish.org` |
| asrax / prod-style | `https://lago.asrax.in` |

**Login:** Lago admin user (`LAGO_ADMIN_EMAIL` / password from vault/secrets — never commit). Signup is disabled.

**How to find one user’s plan**

1. Get Keycloak user id (`sub`) from Keycloak admin or support tool.  
2. Open Lago → **Customers**.  
3. Search external id: **`am-user-{keycloakUserId}`**.  
4. Open customer → **Subscriptions** → plan code (e.g. `am_pro`, `am_free`) and status.  
5. Subscription external id is typically **`am-sub-{keycloakUserId}`**.

**How to browse many users**

- Lago → **Customers** / **Subscriptions** lists (paginated).  
- This is the only built-in “all users’ plans” view today.

**APIs (ops / service token — not a panel)**

| Call | What you get |
|------|----------------|
| `GET /subscriptions/me` | Current user only (JWT) |
| `GET /subscriptions/internal/entitlements/{user_id}` | Plan + entitlements for one user |
| `GET /subscriptions/plans` | Catalog only |

**Not in Hub admin (`:8130`):** no billing / subscription page.

**Keycloak admin:** users and email only — **not** plan/trial.

### 16.2 Gap for trial + referral (after v1.1 ships)

Lago shows **plan code** (`am_pro`) but **not** (unless we sync metadata — §16.5):

- `grant_source` (`trial` / `referral` / `paid`)
- `trial_pro_expires_at` / `referral_pro_expires_at`
- referral code / qualified_count / attribution history

Those live in **am-subscription Postgres** once implemented.

### 16.3 How we solve ops visibility (plan)

| Priority | Deliverable | Purpose |
|----------|-------------|---------|
| P0 (now) | Use Lago Customers as above | See who is on which plan |
| P1 | Ensure `ensure_customer` stores **email** on Lago customer | Search by email in Lago |
| P1 | Sync Lago customer **metadata** (see §16.5) | See referral/trial tags inside Lago UI |
| P1 | Expose on `GET /subscriptions/me` (+ internal by `user_id`): `grant_source`, expiries, `referral_code_used` | App + support |
| P2 | Internal ops: `GET /subscriptions/internal/users/{user_id}/subscription` + `.../referrals` | Test vs real user deep dive |
| P2 | `GET /subscriptions/internal/referrals?env=&status=&limit=` | List attributions (filter test/prod) |
| P3 | Small admin page listing email, plan, grant_source, expiries, referral remaining | Growth/support console |

**Support runbook (target)**

1. User reports plan/referral issue → find Keycloak id / email.
2. Lago: confirm plan code / status + metadata tags.
3. AM internal API: confirm `grant_source` + expiries + referral history.
4. Never edit Lago plan manually for trial/referral without matching AM grant rows (drift risk).
5. For **custom paid discounts**, use Lago coupons (§18) — not manual plan hacks.

### 16.4 Acceptance for ops visibility

- [ ] Documented Lago lookup (`am-user-{id}`) in this plan
- [ ] After grant work: internal get-by-`user_id` returns trial/referral fields
- [ ] Lago customer metadata shows referral/trial tags for test and prod users
- [ ] (Optional P3) Admin list UI — follow-up, not v1 ship blocker

### 16.5 Lago metadata — see test vs actual referrals

On every trial/referral grant, `am-subscription` updates Lago customer (`am-user-{id}`) metadata (and keeps email):

| Metadata key | Example | Use |
|--------------|---------|-----|
| `am_env` | `dev` / `preprod` / `prod` | Separate test vs actual |
| `am_grant_source` | `trial` / `referral` / `paid` | Why they have Pro |
| `am_referral_code_used` | `ABC123` | Referee: which invite |
| `am_referrer_user_id` | Keycloak sub | Who referred |
| `am_qualified_count` | `3` | Referrer progress (updated on reward) |
| `am_trial_expires_at` | ISO UTC | Trial end |
| `am_referral_expires_at` | ISO UTC | Referral banked end |
| `am_is_test_user` | `true`/`false` | Optional flag (email domain / allowlist / Keycloak attribute) |

**How ops sees referrals in Lago**

1. Open Lago → **Customers**.
2. Filter/search by email or `am-user-{uuid}`.
3. Read metadata + subscription plan.
4. For full history (pending/rejected), use AM internal referrals API (Lago is a summary view, not the ledger).

**Test vs actual**

| Kind | How to mark | How to find |
|------|-------------|-------------|
| Test | `am_env!=prod` and/or `am_is_test_user=true` | Lago metadata / internal API `?env=dev` |
| Actual | `am_env=prod` | Same |

---

## 18. Lago coupons — customize user plans (Phase 6)

### 18.1 Can we generate coupons from Lago?

**Yes.** Lago supports:

- `POST /api/v1/coupons` — create coupon (fixed amount or percentage, plan limits, expiry)
- `POST /api/v1/applied_coupons` — apply coupon to customer `external_id` = `am-user-{id}`

Docs: [Create coupon](https://docs.getlago.com/api-reference/coupons/create), [Apply coupon](https://docs.getlago.com/api-reference/coupons/apply).

### 18.2 What coupons are for (vs trial/referral)

| Mechanism | Use |
|-----------|-----|
| AM timed Pro grant (v1 Phases 1–3) | Free **trial** / **referral** Pro days (no invoice) |
| **Lago coupon (Phase 6)** | **Discount on paid invoices** — customize a user's paid plan price (e.g. 50% off `am_pro` for 3 months, VIP deal, partner code) |

Do **not** replace trial/referral with coupons in v1 — coupons do not replace entitlement grants cleanly for free Pro windows.

### 18.3 AM ownership (keep loose coupling)

```text
Ops / admin → am-subscription internal API → LagoProvider.create_coupon / apply_coupon → Lago
App (optional later) → redeem public coupon code → subscription → apply_coupon
```

- Identity never talks to Lago.
- Coupon codes are **billing discounts**, distinct from **referral invite codes**.
- Store mapping in AM: `coupon_redemptions` (user_id, lago_coupon_code, applied_at, actor).

### 18.4 Planned APIs (Phase 6)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/subscriptions/internal/coupons` | Create Lago coupon (service JWT) |
| POST | `/subscriptions/internal/coupons/apply` | Apply to `user_id` / `am-user-{id}` |
| GET | `/subscriptions/internal/users/{user_id}/coupons` | List applied coupons |
| POST | `/subscriptions/coupons/redeem` (optional user JWT) | User enters ops-issued code |

Example apply body:

```json
{
  "user_id": "kc-sub",
  "coupon_code": "VIP_PRO_50_3M",
  "idempotency_key": "coupon:{user_id}:{coupon_code}"
}
```

### 18.5 Ops workflow — customize a user's plan

1. Decide discount (amount/% , duration, which plan codes).
2. Create coupon in Lago (UI or AM internal API).
3. Apply to customer `am-user-{id}` **before** or during paid subscription (apply then subscribe/upgrade sequentially).
4. Confirm in Lago customer → **Coupons** + next invoice preview.
5. Optionally set metadata `am_custom_offer=VIP_PRO_50_3M`.

### 18.6 Acceptance (Phase 6)

- [ ] Create + apply coupon via AM → visible on Lago customer
- [ ] Discount appears on paid invoice for `am_pro`
- [ ] Idempotent re-apply does not double-discount
- [ ] Referral invite codes remain separate from Lago coupon codes
- [ ] Test env coupons cannot be applied to prod customers (`am_env` check)

---

## 17. Loopholes — closed in plan (locked mitigations)

Every known loophole from design review is addressed below. **Closed in plan** means implementers must build these controls; residual risk is called out.

| ID | Loophole | Locked fix (v1) | Residual |
|----|----------|-----------------|----------|
| **L1** | Disposable-email farm → free 30d Pro | `TRIAL_GRANT_DELAY_HOURS` default **24**; metrics + alert on trial spike; optional disposable-domain deny list flag | Motivated farms still possible slower |
| **L2** | Spoofable `device_id` | Require UUID ≥16 chars for referral; reject empty/`unknown`; unique device on attributions; backlog Play Integrity / App Attest | Emulators can still mint UUIDs |
| **L3** | Self-referral via alt email | Reject `self_referral` (same user_id); reject if normalized referee email == referrer email; reject device if ever used by referrer or prior referee | Truly distinct emails+devices still work (by design of invites) |
| **L4** | 12×14d stacking farm | Lifetime cap **12** + **3 rewards / referrer / UTC day** + referrer reward delay 24h | Slow farms still hit cap |
| **L5** | Single `grant_source` clobber | Sticky **`is_paid`**; trial/referral expiries separate; display source never clears paid | Must be tested |
| **L6** | Paid mid-trial / cancel mid-referral | Paid → no downgrade; on cancel, remain Pro until `max(trial, referral)` if still future (banked days) | Product copy must explain |
| **L7** | Bootstrap vs trial double grant | Bootstrap/free on create; **trial only** on email_verified grant path; idempotent `trial:{user_id}` | — |
| **L8** | Kafka order (verify before register consumed) | `email_verified` payload repeats `referral_code`/`device_id`/`email`; consumer **upserts** pending then qualifies | — |
| **L9** | Lago drift | Retryable Lago sync / outbox; daily reconcile job; **forbid** manual Lago plan edits without AM grant rows | Manual ops mistakes |
| **L10** | Deep-link drops `ref` | Deferred deep link required; funnel `ref_captured` vs `ref_attributed`; FAQ | Some store loss remains |
| **L11** | Weak web device | Web also generates persistent localStorage UUID; same referral rules; no skip | Shared browsers |
| **L12** | Delete account → new trial same email | Unique **`trial_email_fingerprint`** (normalized email hash) | New email = new trial |
| **L13** | Leaked internal grant API | Service JWT + audience only; deny user JWT; audit all grants | Compromised service token |
| **L14** | Ambiguous “30 days” | Locked: **30 × 24 hours UTC** from verified_at (+ delay) | — |
| **L15** | Referrer already paid — reward “invisible” | Always write `referral_rewards` + extend `referral_pro_expires_at` (banked); UI: “+14d banked if you leave paid” | — |

### 17.1 Implementer checklist (must pass before saying “loopholes fixed in code”)

- [ ] L1 delay + metrics  
- [ ] L2/L11 device UUID rules  
- [ ] L3 email + device graph rejects  
- [ ] L4 daily + lifetime caps  
- [ ] L5/L6 `is_paid` + banked days tests  
- [ ] L7 no trial on bootstrap alone  
- [ ] L8 out-of-order Kafka test  
- [ ] L9 Lago retry + reconcile stub  
- [ ] L10 deferred link analytics  
- [ ] L12 email fingerprint unique  
- [ ] L13 service-auth on grant routes  
- [ ] L14 duration unit tests (720h)  
- [ ] L15 paid referrer still banks +14d  

### 17.2 Re-rate after loophole lock

| Score | Value |
|-------|------:|
| Design now (rules locked, code missing) | **9.1** |
| After §17 built + tested in staging | **9.4–9.5** |
| Perfect 10 | Still needs hardware attestation + near-zero deep-link loss |

---

## 19. Pre-coding locks (must not invent during PRs)

These close the last “we forgot that” gaps before Phase 3. **Locked 2026-09-13.**

### 19.1 Delayed grant runner

| Decision | Lock |
|----------|------|
| Mechanism | Table `grant_schedules` (`id`, `user_id`, `kind=trial\|referral_reward`, `payload_json`, `execute_at`, `status=pending\|done\|cancelled`, `idempotency_key`) |
| Worker | `am-subscription` **background poller** (every 30–60s) — same process or sidecar; **not** sleep-in-Kafka-consumer |
| Why not Temporal (v1) | `am-subscription` has no Temporal worker today; avoid new infra for v1 |
| Later | May migrate schedules to Temporal without changing product rules |
| Delay=0 | Tests / local: execute immediately in-process (still write schedule row as `done` for audit) |

On `email_verified`: enqueue trial (+ referral reward if pending) with `execute_at = now + TRIAL_GRANT_DELAY_HOURS`. Poller calls unified `pro-days` / qualify paths idempotently.

### 19.2 Signup paths (email + Google / social)

| Path | When trial + referral run |
|------|---------------------------|
| Email/password register | After **email verified** event (as today) |
| Google / social where email is **already verified** at account create | Emit `email_verified` (or equivalent) **once** at first successful identity proof — same consumers |
| Google with unverified email (rare) | Wait until verified — same as email path |

**Rule:** One logical “email proven” moment per user → one trial. Referral attribute still only if `referral_code` present at **register** (or first identity link for that user — v1: register/social-signup payload only; no later attach).

Flutter must pass `referral_code` + `device_id` on **all** first-account creation flows (email and Google).

### 19.3 UX during trial delay

| Moment | User sees |
|--------|-----------|
| Just verified, delay > 0 | Plan still free / “Pro trial starts soon”; banner: trial activates in ~Nh |
| After poller grants | Entitlements = `am_pro`; notify `trial_started` |
| Settings / subscription UI | Show `trial_starts_at` / `trial_pro_expires_at` when pending |

Do **not** silently leave users thinking they have Pro during the delay window.

### 19.4 Invite code format

| Rule | Value |
|------|-------|
| Alphabet | `A-Z` `2-9` (no `0/O/1/I`) |
| Length | **8** characters |
| Case | Stored uppercase; input case-insensitive |
| Generation | Retry on unique collision |
| Distinct from | Lago **coupon** codes (different prefix optional: invite has no `VIP_` prefix requirement; coupons use ops-chosen codes) |

### 19.5 Canonical share URL

| Env | URL pattern |
|-----|-------------|
| Prod | `https://asrax.in/download?ref={CODE}` |
| Other | From config `REFERRAL_SHARE_BASE_URL` + `?ref={CODE}` |

Store listing / deferred deep link must preserve `ref` into app install storage. Flutter reads `ref` then clears only after successful register send (or keep until register succeeds).

### 19.6 Privacy — Settings history

| Show | Do not show (v1) |
|------|------------------|
| Date, status (`pending`/`rewarded`/`rejected`), masked code if needed | Full invitee email / phone / name |

Optional later: first name only with explicit consent — **not** v1.

### 19.7 First-run referrer identity

| Show | Source |
|------|--------|
| Invite **CODE** (required) | Attribution |
| Referrer display name | **Not in v1** (avoids identity lookup / PII). Copy: “You joined with invite **CODE**.” |

### 19.8 Deploy / gateway / flags

| Item | Lock |
|------|------|
| Gateway | Route new `/subscriptions/referrals/*` and internal grant/referral paths like existing subscription routes |
| OpenAPI / Postman | Update when APIs land |
| Vault / helm | `TRIAL_GRANT_DELAY_HOURS`, `REFERRAL_REWARD_DELAY_HOURS`, `REFERRAL_SHARE_BASE_URL`, Lago keys (existing), Kafka |
| GrowthBook (optional) | `referral_ui_enabled`, `trial_delay_hours` override — default on in staging |
| Existing users | **No trial backfill** |

### 19.9 Notification during delay

| Event | When |
|-------|------|
| Optional `trial_scheduled` | On verify (delay > 0) — “Your Pro trial starts in 24h” |
| `trial_started` | When grant actually applies |
| `referral.rewarded` | When referrer +14d applies (after delay) |

### 19.10 Coding order (do not skip)

1. Phase 1 identity + Kafka  
2. Phase 2 schema + attribute/qualify (no grants yet OK)  
3. Phase 3 `grant_schedules` + poller + pro-days + expiry  
4. Phase 4 Flutter first (notification deferred)  
5. Phase 5 Lago metadata  
6. Phase 6 coupons (optional)

---

## 20. Coding TODO checklist (single-file workflow)

**Use this section to implement.** Rules live in §§1–19 above; checkboxes and file lists live here.  
Work **phase by phase**. Do not start Phase 3 until Phase 1 exit gate is green.

**How to use:** Open only `plan_referral_implementation.md` → jump to **§20** → code → tick boxes.

| Anchor | Value |
|--------|--------|
| Trial | 30×24h after email proven (+ delay) |
| Referrer | +14×24h; cap 12 + 3/day |
| Delay runner | `grant_schedules` + poller (§19.1) |
| UI | First-run CODE + Settings → Referral (§9) |
| Ops | Lago metadata (§16.5); coupons Phase 6 (§18) |

Diagrams: [design/referral-system.drawio](./design/referral-system.drawio).

### Phase 0 — Docs & alignment

#### Steps

1. Confirm plan §§1, 9, 16.5, 17, 18, **19** are accepted by eng + product.
2. Confirm draw.io opens; README links this file.
3. Create tracking tickets: `P1-identity`, `P2-ledger`, `P3-grants`, `P4-flutter`, `P5-lago-meta`, `P6-coupons`.

#### Done when

- [x] Plan §19 locked (delay runner, social signup, delay UX, code format, share URL)
- [x] This detailed TODO merged into §20 of this plan
- [x] Team agrees: Phase 1 first, no grant code before Kafka green

---

### Phase 1 — Identity: capture + Kafka (ship gate)

**Repo:** `am-platform/am-identity`  
**Exit gate:** Both Kafka events visible in staging with required fields.

#### 1.1 Files to touch

| File | Change |
|------|--------|
| `am_identity/schemas/auth.py` | Add optional `referral_code`, `device_id` to register (and social signup DTO if separate) |
| `am_identity/api/auth_router.py` | Accept fields; do not validate code existence |
| Keycloak / Google signup path | Pass through same fields on first account create |
| `am_identity/core/kafka.py` | Publish ADR-style events |
| OpenAPI / tests | Schema + unit tests |

#### 1.2 Steps

1. Extend register (and Google/social first-signup) request body:
   - `referral_code: str | None`
   - `device_id: str | None`
2. After user create → publish `am.identity.user_registered.v1`:
   - `user_id`, `email`, `referral_code?`, `device_id?`, `correlation_id`, `event_id`, `idempotency_key`
3. On email proven (verify link **or** Google verified-at-create) → publish `am.identity.email_verified.v1` **once**:
   - Must **repeat** `email`, `referral_code?`, `device_id?` (for out-of-order consumers)
4. Do **not** add attach-later or reinstall-restore APIs.
5. Gateway: ensure auth routes still work (no subscription dependency).

#### 1.3 Tests

- [x] Register without code succeeds
- [x] Register with garbage code still creates account
- [x] Event payload includes code when provided
- [x] Google verified path emits verify event once
- [x] No second `email_verified` on re-login

#### 1.4 Done when

- [ ] Staging: consume/log both event types
- [x] OpenAPI shows new optional fields
- [x] **Phase 2 may start** (unit gate green; staging Kafka still open)

---

### Phase 2 — Subscription: referral ledger (no Pro grant yet)

**Repo:** `am-platform/am-subscription`  
**Exit gate:** Attribute/qualify state machine + caps work without calling Lago Pro grant (qualify may stop at `qualified` until Phase 3).

#### 2.1 Migrations / tables

Implement per plan §4:

| Table | Key columns |
|-------|-------------|
| `referral_codes` | `user_id` unique, `code` unique (8-char §19.4), `qualified_count`, `status` |
| `referral_attributions` | `referee_user_id` unique, `referrer_user_id`, `code`, `device_id`, `status`, `reject_reason` |
| `referral_rewards` | referrer beneficiary, `days=14`, `idempotency_key`, timestamps |

Indexes: referrer+status; unique partial `device_id`; daily reward count support.

#### 2.2 Domain rules to code

1. Get-or-create code for user (`GET /subscriptions/referrals/me`).
2. On `user_registered` → **attribute**:
   - Invalid/missing code → no row (or reject invalid)
   - Self / same-email / device used / cap 12 / daily 3 → `rejected` + reason
   - Else `pending`
3. On qualify input (from verify consumer in Phase 3) → `qualified` → later `rewarded`.
4. Row lock referrer code row when counting cap.

#### 2.3 APIs

| Method | Path | Notes |
|--------|------|-------|
| GET | `/subscriptions/referrals/me` | code, share URL (`REFERRAL_SHARE_BASE_URL`), counts, remaining |
| GET | `/subscriptions/referrals/me/history` | date, status only — **no invitee email** (§19.6) |
| POST | `/subscriptions/internal/referrals/attribute` | service JWT |
| POST | `/subscriptions/internal/referrals/qualify` | service JWT (full reward in Phase 3) |

#### 2.4 Consumer (register only in this phase)

- Topic `am.identity.events.v1` → attribute pending.
- Idempotent by `event_id` / `idempotency_key`.

#### 2.5 Tests

- [x] Valid code → pending
- [x] Self / same email / device → rejected
- [x] Cap 12 / 3 per day
- [x] Missing device_id → no attribution
- [x] History has no PII emails

#### 2.6 Done when

- [x] Migration applies cleanly (`create_all` adds `am_referral_*` tables — repo pattern)
- [x] `/referrals/me` returns stable code + share URL
- [ ] Register consumer creates pending in staging

---

### Phase 3 — Timed Pro: schedules, trial, referrer reward, expiry

**Repo:** `am-subscription` (+ Lago provider)  
**Exit gate:** Paid never downgraded; delays work via poller; loophole tests L5–L9, L12–L15 green.

#### 3.1 Additional schema

| Piece | Purpose |
|-------|---------|
| Subscription fields | `is_paid`, `trial_pro_expires_at`, `referral_pro_expires_at`, `trial_email_fingerprint`, `trial_starts_at` (optional) |
| `grant_schedules` | §19.1 delayed execution |
| Outbox / retry | Lago sync failures |

#### 3.2 Unified grant API

`POST /subscriptions/internal/grants/pro-days`

| reason | Behavior |
|--------|----------|
| `trial` | Idempotent `trial:{user_id}`; set fingerprint; expiries = execute_at + 30×24h |
| `referral` | Idempotent `ref-reward:{attribution_id}:referrer`; extend referral expiry +14×24h |

Algorithm: sticky `is_paid`; never downgrade paid; bank referral days (§17 L5/L6/L15).

#### 3.3 email_verified consumer

1. Upsert pending attribution if code in payload (L8).  
2. Insert `grant_schedules` for trial (+ referral reward if pending).  
3. If delay=0 → run immediately.  
4. Optional emit `trial_scheduled` if delay>0 (§19.9).

#### 3.4 Poller

- Every 30–60s: claim due `grant_schedules`, execute, mark done.  
- Emit `trial_started` / `referral.rewarded` when applied.

#### 3.5 Expiry worker

- If `is_paid` → skip.  
- Else if now > max(trial, referral) → revert free + Lago sync.

#### 3.6 Bootstrap coexistence

- `get_or_create` may create free; **trial only** via grant path (L7).

#### 3.7 Config (Vault / helm)

- `TRIAL_GRANT_DELAY_HOURS` (default 24)  
- `REFERRAL_REWARD_DELAY_HOURS` (default 24)  
- `REFERRAL_SHARE_BASE_URL`  
- Existing Lago + Kafka settings  

#### 3.8 Tests (required)

- [x] 720h duration math  
- [x] Delay schedule then poller applies  
- [x] Same email fingerprint blocks second trial (incl. Gmail +alias)  
- [x] Out-of-order verify upserts pending  
- [x] Paid sticky + banked days after cancel  
- [x] User JWT rejected on internal grant (route uses `require_service_account`)  
- [ ] Cap race under parallel qualify  

#### 3.9 Done when

- [ ] Staging: verify → wait/delay → Pro in AM + Lago  
- [ ] Referrer receives +14d after delay  
- [x] §17.1 checklist mostly green (unit)  

---

### Phase 4 — Notification + Flutter (`am-modern-ui`)

**Repos:** `am-notification`, `am-modern-ui`  
**Exit gate:** First-run CODE + Settings Referral + share path work on device.

#### 4.1 Notification — **SKIPPED / deferred**

Notification module not fully working; Novu mappings deferred. Events can still be emitted later; UI does not depend on them.

| Event | Novu / mapping | Status |
|-------|----------------|--------|
| `trial_scheduled` (optional) | Delay copy | Deferred |
| `trial_started` | Trial active | Deferred |
| `referral.rewarded` | Referrer +14d | Deferred |
| `referral.qualified` | Optional | Deferred |

Files: `am_notification/.../event_mapping.py` + Novu workflows — **do not block Flutter**.

#### 4.2 Flutter — capture

1. [x] Generate install-scoped UUID `device_id` (`ReferralInstallStore`).  
2. [x] Read `?ref=` at web/bootstrap launch → store until register succeeds (mobile App Links / deferred deep link still follow-up).  
3. [x] Pass `referral_code` + `device_id` on **email and Google** first signup (§19.2).  
4. [x] Analytics: `ref_captured` ( `ref_attributed` when backend confirms — later).

#### 4.3 Flutter — first-run (§9.2)

1. [x] After login, if `joined` present and intro not seen → sheet with **CODE** only (§19.7).  
2. [x] Dismiss → persist flag.  
3. [x] Data from `GET /subscriptions/referrals/me` → `joined`.

#### 4.4 Flutter — Settings → Referral (§9.3)

1. [x] Your code + copy invite URL (`share_url` from API).  
2. [x] `qualified_count` / remaining of 12.  
3. [x] History: date + status only (no emails).  
4. [ ] Note if banked referral days while paid (needs grant fields on `/me` — follow-up with delay banner).

#### 4.5 UX during delay (§19.3)

- [ ] Banner / subscription card: trial pending vs active using `trial_starts_at` / expiries.

#### 4.6 Gateway

- [ ] Ensure app JWT can call `/subscriptions/referrals/me` and `/me` with new fields (verify in staging).

#### 4.7 Tests / manual QA

- [x] Unit: `ReferralInstallStore` + referral DTO parse  
- [ ] Cold install with ref → register → CODE on first-run once  
- [ ] Settings shows counts after reward  
- [ ] Redownload → no ref  
- [ ] Google signup with ref works  
- [ ] Delay banner then Pro after grant  

#### 4.8 Done when

- [ ] E2E on staging build  
- [ ] Product sign-off on copy  
- Flutter Settings + first-run + capture: **implemented in code** (manual QA / staging pending)  
- Notification 4.1: **explicitly skipped**

---

### Phase 5 — Lago metadata + ops APIs

#### 5.1 Steps

1. Extend `LagoProvider.ensure_customer` / update to set metadata (§16.5).  
2. On trial/referral grant: push `am_env`, `am_grant_source`, `am_referral_code_used`, counts, expiries, `am_is_test_user`.  
3. Internal:
   - `GET /subscriptions/internal/users/{user_id}/subscription`
   - `GET /subscriptions/internal/users/{user_id}/referrals`
   - `GET /subscriptions/internal/referrals?env=&status=`
4. Document runbook for ops (Lago + API).

#### 5.2 Checks

- [ ] Test user: `am_env=dev|preprod` in Lago UI  
- [ ] Prod user: `am_env=prod`  
- [ ] Referee metadata shows code used  
- [ ] Full pending/rejected history only via AM API  

#### 5.3 Done when

- [ ] Support can distinguish test vs actual referrals without DB access  

---

### Phase 6 — Lago coupons (optional paid customization)

See plan §18. Do **after** Phases 1–4 stable.

#### 6.1 Steps

1. `create_coupon` / `apply_coupon` on `LagoProvider`.  
2. Internal APIs + `coupon_redemptions` table.  
3. Env guard: no cross-env apply.  
4. Optional user `POST /subscriptions/coupons/redeem`.

#### 6.2 Checks

- [ ] Coupon on Lago customer  
- [ ] Paid invoice discounted  
- [ ] Invite code ≠ coupon code in UI  

---

### Cross-cutting checklist (every PR)

- [ ] No identity → subscription HTTP  
- [ ] No secrets in repo / chat (`credentials`, Lago admin keys)  
- [ ] Vault mapping for new env vars  
- [ ] Gateway + OpenAPI updated for new public routes  
- [ ] Idempotent Kafka / grants  
- [ ] Tests for happy + reject paths  

---

### Full regression matrix

| # | Scenario | Expected |
|---|----------|----------|
| 1 | New user verifies (no ref) | Trial after delay; 30×24h |
| 2 | Valid ref + device | Trial + referrer +14×24h after delays |
| 3 | 13th lifetime | `referrer_cap_reached` |
| 4 | 4th same UTC day | daily limit |
| 5 | Self / same email / device | rejected |
| 6 | No device_id | no attribution |
| 7 | Gmail `a+1@` after `a@` | no second trial |
| 8 | Verify before register consumed | upsert; works |
| 9 | Paid + expiry job | stays Pro |
| 10 | Cancel paid + banked referral | Pro until referral end |
| 11 | Bootstrap only | free until verify grant |
| 12 | User JWT on grant | 403 |
| 13 | Redownload | no referral |
| 14 | Kafka replay | idempotent |
| 15 | Invalid code | account + trial OK |
| 16 | First-run UI | CODE once |
| 17 | Settings Referral | count + history no PII |
| 18 | Delay window | no silent Pro; banner |
| 19 | Google signup + ref | events + attribution |
| 20 | Lago metadata | test vs prod tags |
| 21 | VIP coupon (P6) | invoice discount |

---

### Definition of done (launch)

| Milestone | Required |
|-----------|----------|
| Soft launch | Phases **1–4** green + matrix 1–19 |
| Ops ready | Phase **5** metadata |
| Custom paid offers | Phase **6** when product asks |

**Do not** call the system “done” on docs score alone — staging matrix must pass.

