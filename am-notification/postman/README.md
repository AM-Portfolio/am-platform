# AM Notification — Postman

Import:

- `AM-Notification.postman_collection.json`
- `AM-Notification.local.postman_environment.json`

## Setup

1. Copy `AM_NOTIFICATION_CLIENT_SECRET` from `am-platform/.secrets.env` into Postman env as `notification_client_secret`.
2. Start the service: `npm run notification:dev` from `am-platform/`.
3. Run **99 Keycloak Helpers → Client Credentials (am-notification-service)**.
4. Run **03 Internal → Send Notification** — triggers Novu workflow `identity-login-new-device`.

## User inbox routes

Obtain a user JWT from the AM Identity collection, set `access_token`, then use **01 Inbox** requests.
