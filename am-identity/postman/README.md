# AM Identity — Postman source

This folder is the **source** for the Identity module inside **AM Platform**.

Do **not** import `AM-Identity.postman_collection.json` into Postman. Import `am-platform/postman/AM-Platform.postman_collection.json` instead. Importing both duplicates every identity request.

To apply changes:

```bash
cd am-platform
python postman/build_platform_postman.py
python postman/scripts/sync_platform_postman.py
```

## Local identity only (optional)

If you must hit identity in isolation without the unified collection, still prefer AM Platform with the Local env (`identity_base_url=http://localhost:8113`).

```bash
cd am-platform/am-identity
npm run dev
```

Service listens on **http://localhost:8113**.

## Login platforms

Identity → **Auth** → **Login & Session** → **Login**.

| Request | `platform` | Refresh `client_id` |
|---------|------------|---------------------|
| Login (Web) | `web` | `am-web-client` |
| Login (Android) | `android` | `am-android-client` |
| Login (iOS) | `ios` | `am-ios-client` |

Then **Refresh → Last login**. OTP: **Auth → Web OTP** (`/auth/web/otp/*`). `/auth/login/otp` is a 501 stub under **Auth → Deprecated**.

QR without a phone: **Flows → QR login (no phone)**.
