#!/usr/bin/env bash
# Idempotent Keycloak setup for Flutter Google id_token login via am-identity.
#
# am-identity validates the Google JWT, provisions the user, then issues realm
# tokens via direct impersonation (required on Keycloak 26.3; native JWT bearer
# grant needs Keycloak 26.5+).
#
# Usage (kubectl access to the cluster required):
#   ./automation/scripts/setup-keycloak-google-login.sh google-login
#   ./automation/scripts/setup-keycloak-google-login.sh hostname
#   ./automation/scripts/setup-keycloak-google-login.sh all
#
# Environment overrides:
#   KEYCLOAK_NS=identity
#   KEYCLOAK_POD=keycloak-0
#   KEYCLOAK_REALM=am-preprod-realm
#   KEYCLOAK_HOSTNAME=https://auth.munish.org/auth
#   IDENTITY_CLIENT_ID=am-identity-service
#   KEYCLOAK_ADMIN_PASSWORD=...   (default: read from keycloak pod secret file)

set -euo pipefail

KEYCLOAK_NS="${KEYCLOAK_NS:-identity}"
KEYCLOAK_POD="${KEYCLOAK_POD:-keycloak-0}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-am-preprod-realm}"
KEYCLOAK_HOSTNAME="${KEYCLOAK_HOSTNAME:-https://auth.munish.org/auth}"
KEYCLOAK_FEATURES="${KEYCLOAK_FEATURES:-token-exchange,admin-fine-grained-authz:v1}"
IDENTITY_CLIENT_ID="${IDENTITY_CLIENT_ID:-am-identity-service}"
KCADM=/opt/bitnami/keycloak/bin/kcadm.sh

usage() {
  sed -n '2,12p' "$0"
  echo "Commands: google-login | hostname | all"
}

kc_exec() {
  kubectl exec -n "$KEYCLOAK_NS" "$KEYCLOAK_POD" -- "$@"
}

admin_password() {
  if [[ -n "${KEYCLOAK_ADMIN_PASSWORD:-}" ]]; then
    printf '%s' "$KEYCLOAK_ADMIN_PASSWORD"
    return
  fi
  kc_exec cat /opt/bitnami/keycloak/secrets/admin-password 2>/dev/null \
    || printf '%s' "adminpassword123"
}

run_kcadm_in_pod() {
  local admin_pass
  admin_pass="$(admin_password)"
  kc_exec env KEYCLOAK_ADMIN_PASSWORD="$admin_pass" KEYCLOAK_REALM="$KEYCLOAK_REALM" \
    IDENTITY_CLIENT_ID="$IDENTITY_CLIENT_ID" bash -s <<'INPOD'
set -euo pipefail
export HOME=/tmp
mkdir -p /tmp/.keycloak
K=/opt/bitnami/keycloak/bin/kcadm.sh
REALM="$KEYCLOAK_REALM"
CLIENT_ID="$IDENTITY_CLIENT_ID"
$K config credentials \
  --server http://127.0.0.1:8080/auth \
  --realm master \
  --user admin \
  --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null

echo "=== Google IdP: issuer + JWKS signature validation ==="
$K update identity-provider/instances/google -r "$REALM" \
  -s 'config.validateSignature=true' \
  -s 'config.useJwksUrl=true' \
  -s 'config.issuer=https://accounts.google.com'

echo "=== Enable user impersonation permissions (realm) ==="
$K update users-management-permissions -r "$REALM" -s enabled=true 2>/dev/null \
  || $K create users-management-permissions -r "$REALM" -s enabled=true 2>/dev/null \
  || true

CLIENT_UUID=$($K get clients -r "$REALM" -q clientId="$CLIENT_ID" --fields id --format csv --noquotes | tail -1)
RM_ID=$($K get clients -r "$REALM" -q clientId=realm-management --fields id --format csv --noquotes | tail -1)
POLICY_NAME="allow-${CLIENT_ID}-impersonation"

echo "=== Client policy: $POLICY_NAME ==="
$K create "clients/$RM_ID/authz/resource-server/policy/client" -r "$REALM" \
  -s name="$POLICY_NAME" \
  -s type=client \
  -s logic=POSITIVE \
  -s decisionStrategy=UNANIMOUS \
  -s "clients=[\"$CLIENT_UUID\"]" 2>/dev/null || true

POLICY_ID=$($K get "clients/$RM_ID/authz/resource-server/policy" -r "$REALM" \
  -q name="$POLICY_NAME" --fields id --format csv --noquotes | tail -1)
IMP_ID=$($K get users-management-permissions -r "$REALM" --fields scopePermissions \
  | sed -n 's/.*"impersonate"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

if [[ -z "$POLICY_ID" || -z "$IMP_ID" ]]; then
  echo "ERROR: could not resolve policy_id or impersonate permission id" >&2
  exit 1
fi

echo "=== Attach impersonation policy (permission=$IMP_ID) ==="
$K update "clients/$RM_ID/authz/resource-server/permission/scope/$IMP_ID" -r "$REALM" \
  -s "policies=[\"$POLICY_ID\"]" \
  -s decisionStrategy=UNANIMOUS

echo "=== Done. Google IdP + impersonation for $CLIENT_ID on realm $REALM ==="
INPOD
}

patch_hostname() {
  echo "=== Patch Keycloak hostname + preview features ==="
  kubectl patch configmap keycloak-env-vars -n "$KEYCLOAK_NS" --type merge -p "{
    \"data\": {
      \"KC_HOSTNAME\": \"$KEYCLOAK_HOSTNAME\",
      \"KC_FEATURES\": \"$KEYCLOAK_FEATURES\"
    }
  }"
  kubectl set env statefulset/keycloak -n "$KEYCLOAK_NS" "KC_HOSTNAME=$KEYCLOAK_HOSTNAME"
  kubectl rollout restart statefulset/keycloak -n "$KEYCLOAK_NS"
  kubectl rollout status statefulset/keycloak -n "$KEYCLOAK_NS" --timeout=180s
  echo "KC_HOSTNAME=$(kubectl get configmap keycloak-env-vars -n "$KEYCLOAK_NS" -o jsonpath='{.data.KC_HOSTNAME}')"
  echo "KC_FEATURES=$(kubectl get configmap keycloak-env-vars -n "$KEYCLOAK_NS" -o jsonpath='{.data.KC_FEATURES}')"
}

main() {
  local cmd="${1:-google-login}"
  case "$cmd" in
    -h|--help|help) usage; exit 0 ;;
    google-login) run_kcadm_in_pod ;;
    hostname) patch_hostname ;;
    all)
      patch_hostname
      run_kcadm_in_pod
      ;;
    *)
      echo "Unknown command: $cmd" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
