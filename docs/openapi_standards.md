# OpenAPI Standards & API Guidelines

This document details the REST API conventions, versioning policy, and error/success envelope patterns for the `am-platform` ecosystem.

## 1. REST API Routing & Versioning

- **Gateway Endpoint Prefixing:**
  All public routes must be prefixed with `/api` and routed via Traefik.
  - Auth/Identity: `/api/auth/*` and `/api/users/*`
  - Subscriptions: `/api/subscriptions/*`
  - Notifications: `/api/notifications/*`
- **Internal APIs:**
  Internal routes must start with `/internal` and are blocked from external access by the Gateway.
- **Versioning Policy:**
  - This is a clean-room redesign (v2-era). No legacy compatibility is supported.
  - New service integrations should use URL versioning (e.g., `/api/v1/` or `/api/v2/`) if structural schema breakages occur.
  - Minor backward-compatible changes (adding fields) do not trigger version bumps.

## 2. Response Envelopes

### Success Single-Item Envelope

```json
{
  "data": {
    "user_id": "usr_123456",
    "email": "user@example.com"
  },
  "meta": {}
}
```

### Paginated List Envelope

```json
{
  "items": [
    {
      "id": "sub_111",
      "tier": "Premium"
    }
  ],
  "total": 1,
  "page": 1,
  "size": 10,
  "pages": 1,
  "meta": {}
}
```

## 3. Error Envelope & Status Codes

All errors returned by the system must serialize into the standard error format:

```json
{
  "error_code": "USER_NOT_FOUND",
  "message": "The user with ID usr_123456 could not be found.",
  "details": {
    "id": "usr_123456"
  }
}
```

### Standard Status Code Mapping

| Status Code | Error Code | Description |
|---|---|---|
| **400 Bad Request** | `BAD_REQUEST` | Generic invalid payload or missing properties |
| **401 Unauthorized** | `UNAUTHORIZED` | Invalid or expired authentication token |
| **403 Forbidden** | `FORBIDDEN` | Insufficient roles or blocked access |
| **404 Not Found** | `NOT_FOUND` | Resource does not exist |
| **409 Conflict** | `CONFLICT` | Entity already exists or state conflict |
| **429 Too Many Requests** | `QUOTA_EXCEEDED` | Rate limits or subscription quota exceeded |
| **500 Internal Error** | `INTERNAL_SERVER_ERROR` | Unexpected backend failures |
