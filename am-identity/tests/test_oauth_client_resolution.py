from am_identity.core.config import IdentitySettings
from am_identity.providers.keycloak_provider import KeycloakIdentityProvider


def _provider() -> KeycloakIdentityProvider:
    settings = IdentitySettings(
        KEYCLOAK_URL="http://localhost/auth",
        KEYCLOAK_REALM="am-realm",
        KEYCLOAK_ADMIN_USER="admin",
        KEYCLOAK_ADMIN_PASSWORD="secret",
        OIDC_TOKEN_URL="http://localhost/auth/realms/am-realm/protocol/openid-connect/token",
        OIDC_ISSUER="http://localhost/auth/realms/am-realm",
        OIDC_JWKS_URL="http://localhost/auth/realms/am-realm/protocol/openid-connect/certs",
        AM_IDENTITY_CLIENT_SECRET="svc-secret",
        GOOGLE_CLIENT_ID="test-google-client",
    )
    return KeycloakIdentityProvider(settings)


def test_android_platform_uses_public_client_without_secret() -> None:
    provider = _provider()
    client_id, secret = provider._resolve_oauth_client(platform="android")
    assert client_id == "am-android-client"
    assert secret is None


def test_refresh_form_includes_refresh_token_only_for_public_client() -> None:
    provider = _provider()
    form = provider._token_form(
        grant_type="refresh_token",
        client_id="am-ios-client",
        refresh_token="rt-1",
    )
    assert form["client_id"] == "am-ios-client"
    assert "client_secret" not in form
    assert form["refresh_token"] == "rt-1"


def test_default_refresh_uses_identity_service_confidential_client() -> None:
    provider = _provider()
    client_id, secret = provider._resolve_oauth_client()
    assert client_id == "am-identity-service"
    assert secret == "svc-secret"
