# Feature: Enterprise Identity Admin + RBAC

| Field | Value |
|-------|--------|
| Status | Spec + APIs/UI in progress with zero-trust pack |
| Target env | `dev` fleet first, then prod/dr |
| Owner area | `am-identity` + `am-modern-ui` + Keycloak TF |
| Related | [ZERO_TRUST_ACCESS.md](../../../am-infra-automation/docs/ZERO_TRUST_ACCESS.md) · fleet [TODO Phase ZT](../../../am-infra-automation/docs/kind-fleet-clusters/TODO.md#phase-zt--zero-trust--identity-admin) |

## Summary

1. Canonical realm roles: `user`, `viewer`, `ops`, `admin`, `super_admin`, `service`.
2. Create / invite from modern-ui defaults to **`user`**, or **`viewer`** (read-only) — never ops/admin on the standard form.
3. Identity Admin console (admin/super_admin only): users, role cards with help text, groups, custom org roles, effective Access summary, audit.
4. Enterprise layers: realm roles → groups → custom composites (product scopes only) → Access policies → API ownership RBAC.
5. Custom roles **cannot** unlock Cloudflare Access admin apps or data-plane TCP.

## Phase tracker

| Phase | Title | Exit criteria |
|-------|--------|---------------|
| D0 | Docs | This file + features README + realm guide delta |
| P0 | MFA enroll | OTP optional; Access off |
| R | Role unify | Fleet aliases → canonical; JWT `roles` claim |
| Create | Create defaults | Invite → `user` or `viewer` only on standard form |
| UI | Identity Admin | Users / Create / Roles / Groups screens |
| Ent | Groups + custom roles APIs | Custom roles cannot grant Access admin/DB |
| V | Smoke | See acceptance below |

## Canonical roles (help copy for console)

| Role | Meaning | Product UI | Identity Admin | Access admin apps | DB TCP |
|------|---------|------------|----------------|-------------------|--------|
| `user` | Default member; own data | Yes (mutations) | No | Deny | Deny |
| `viewer` | Read-only colleague | Yes (reads) | No | Deny | Deny |
| `ops` | Platform SRE | As needed | No | Allow (+ IP) | Allow if registered |
| `admin` | Org identity admin | Yes | Yes (not grant super_admin) | Allow (+ IP) | Allow if registered |
| `super_admin` | Break-glass | Yes | Yes (can grant super_admin) | Allow (+ IP) | Allow if registered |
| `service` | Machines only | N/A | Never on humans | Service Token | N/A |

## Create / invite

| Flow | Default |
|------|---------|
| Self-register / Google SSO | `user` (Keycloak default roles) |
| Identity Admin Create/Invite | Default `user`; radio **Read-only (`viewer`)** |
| Elevated promote | Separate action; audit; admin/super_admin only |

## Identity Admin console (IA)

1. **Users** — list, search, enable/disable, MFA enrolled hint  
2. **Create / Invite** — Member vs Read-only cards; advanced platform roles collapsed  
3. **User detail** — roles, groups, custom roles, effective Access summary  
4. **Roles & permissions** — built-in catalog + custom org roles  
5. **Groups** — org units; default roles on join  
6. **Audit** — who changed whose roles  

## Enterprise layers

```
L1 realm roles (TF-owned names)
  → L2 groups (org/team)
    → L3 custom composites (product scopes only)
      → L4 Access app policies (infra TF + IP registry)
        → L5 API ownership RBAC (each service)
```

## Acceptance

| Test | Expect |
|------|--------|
| Invite default | roles = `["user"]`; Grafana Access deny |
| Invite read-only | roles = `["viewer"]`; mutations 403 |
| `user` → `/admin/users` | 403 |
| Custom role alone | Cannot open store-uis Access or postgres TCP |
| Create form | No ops/admin/super_admin on standard form |

## APIs

- Existing: `GET/POST /admin/users`, roles CRUD — [`am_identity/api/admin_router.py`](../../am-identity/am_identity/api/admin_router.py)
- Extended: groups list/create/assign; custom roles; audit list (see enterprise-rbac implementation)
