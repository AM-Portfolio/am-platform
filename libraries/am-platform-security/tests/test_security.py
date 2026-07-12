import os

from am_platform_security.config import SecuritySettings
from am_platform_security.validator import _issuer_matches, _realm_roles_from_claims


def test_realm_roles_from_claims_reads_realm_access():
    claims = {
        "realm_access": {"roles": ["user", "default-roles-am-realm"]},
    }
    assert _realm_roles_from_claims(claims) == ["user", "default-roles-am-realm"]


def test_security_settings_reads_expected_env_vars():
    os.environ["OIDC_ISSUER"] = "https://issuer.example/realms/am-realm"
    os.environ["OIDC_JWKS_URL"] = "https://issuer.example/realms/am-realm/protocol/openid-connect/certs"
    settings = SecuritySettings()
    assert settings.oidc_issuer.endswith("/am-realm")
    assert settings.oidc_jwks_url.endswith("/certs")


def test_auth_disabled_skips_oidc_requirements(monkeypatch):
    monkeypatch.setenv("AUTH_DISABLED", "true")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    monkeypatch.delenv("OIDC_JWKS_URL", raising=False)
    settings = SecuritySettings()
    assert settings.auth_disabled is True


def test_issuer_matches_http_https_variants():
    configured = "https://auth.munish.org/auth/realms/am-realm"
    token_iss = "http://auth.munish.org/auth/realms/am-realm"
    assert _issuer_matches(token_iss, configured)
    assert _issuer_matches(configured, configured)
    assert not _issuer_matches("http://other.example/realms/am-realm", configured)


def test_token_validator_extracts_userid_claim(monkeypatch):
    import jwt
    from unittest.mock import MagicMock
    from am_platform_security.validator import TokenValidator
    
    settings = SecuritySettings()
    settings.oidc_issuer = "https://issuer.example/realms/am-realm"
    settings.oidc_jwks_url = "https://issuer.example/realms/am-realm/protocol/openid-connect/certs"
    
    validator = TokenValidator(settings)
    
    # Mock JWK client
    mock_key = MagicMock()
    mock_key.key = "mock_public_key"
    monkeypatch.setattr(validator._jwk_client, "get_signing_key_from_jwt", lambda t: mock_key)
    
    # Mock jwt.decode to return claims with userId
    mock_claims = {
        "iss": "https://issuer.example/realms/am-realm",
        "sub": "user-sub-123",
        "userId": "user-id-abc",
        "azp": "am-web-client",
        "scope": "openid email",
        "realm_access": {"roles": ["user"]},
        "token_type": "user",
    }
    monkeypatch.setattr(jwt, "decode", lambda *args, **kwargs: mock_claims)
    
    auth_ctx = validator.validate("fake_token")
    assert auth_ctx.subject == "user-id-abc"
    assert auth_ctx.claims.get("userId") == "user-id-abc"


def test_token_validator_falls_back_to_sub(monkeypatch):
    import jwt
    from unittest.mock import MagicMock
    from am_platform_security.validator import TokenValidator
    
    settings = SecuritySettings()
    settings.oidc_issuer = "https://issuer.example/realms/am-realm"
    settings.oidc_jwks_url = "https://issuer.example/realms/am-realm/protocol/openid-connect/certs"
    
    validator = TokenValidator(settings)
    
    mock_key = MagicMock()
    mock_key.key = "mock_public_key"
    monkeypatch.setattr(validator._jwk_client, "get_signing_key_from_jwt", lambda t: mock_key)
    
    mock_claims = {
        "iss": "https://issuer.example/realms/am-realm",
        "sub": "user-sub-123",
        "azp": "am-web-client",
        "scope": "openid email",
        "realm_access": {"roles": ["user"]},
        "token_type": "user",
    }
    monkeypatch.setattr(jwt, "decode", lambda *args, **kwargs: mock_claims)
    
    auth_ctx = validator.validate("fake_token")
    assert auth_ctx.subject == "user-sub-123"

