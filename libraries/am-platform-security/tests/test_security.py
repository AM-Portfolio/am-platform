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


def test_issuer_matches_http_https_variants():
    configured = "https://auth.munish.org/auth/realms/am-realm"
    token_iss = "http://auth.munish.org/auth/realms/am-realm"
    assert _issuer_matches(token_iss, configured)
    assert _issuer_matches(configured, configured)
    assert not _issuer_matches("http://other.example/realms/am-realm", configured)
