# Identity auth runbook (Phase 7)

## Preprod rollout order

1. Phase 2 — Keycloak TTL apply (terraform)
2. Phase 1 — Flutter client refresh (already on branch)
3. Phase 3 — Mobile app lock
4. Phase 4 — QR login + web OTP
5. Phase 5 — Login alerts
6. Phase 6 — Active sessions UI

## Smoke tests

```bash
# Refresh after login
curl -X POST https://am-dev.asrax.in/identity/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<token>"}'

# Device link start (web)
curl -X POST https://am-dev.asrax.in/identity/auth/device-link/start \
  -H "Content-Type: application/json" \
  -d '{"code_challenge":"<sha256>", "browser": "Chrome", "os": "Windows"}'
```

## Flutter tests

```powershell
cd am-modern-ui/am_auth_ui
flutter test test/core/services/token_refresh_service_test.dart
flutter test test/core/services/app_lock_service_test.dart
flutter test test/features/auth/device_link_poll_service_test.dart
```

## am-identity tests

```powershell
cd am-platform/am-identity
$env:PYTHONPATH=".;../libraries/am-platform-common;../libraries/am-platform-security"
python -m pytest tests/ -q
```

## Prod sign-off checklist

- [ ] Keycloak 7d web / 15d mobile TTL applied
- [ ] Refresh rotation enabled
- [ ] QR login E2E on staging
- [ ] Web OTP rate limits verified
- [ ] Login alert push on new device
- [ ] Session revoke from profile works
