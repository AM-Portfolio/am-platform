from __future__ import annotations

import os

os.environ.setdefault("KEYCLOAK_URL", "http://localhost/auth")
os.environ.setdefault("KEYCLOAK_REALM", "am-realm")
os.environ.setdefault("KEYCLOAK_ADMIN_USER", "admin")
os.environ.setdefault("KEYCLOAK_ADMIN_PASSWORD", "secret")
os.environ.setdefault("OIDC_TOKEN_URL", "http://localhost/auth/realms/am-realm/protocol/openid-connect/token")
os.environ.setdefault("OIDC_ISSUER", "http://localhost/auth/realms/am-realm")
os.environ.setdefault("OIDC_JWKS_URL", "http://localhost/auth/realms/am-realm/protocol/openid-connect/certs")
os.environ.setdefault("AM_IDENTITY_CLIENT_SECRET", "test-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client")
os.environ.setdefault("APP_ENV", "test")
