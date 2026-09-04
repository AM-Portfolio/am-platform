"""Patch prod am-identity OIDC issuer/JWKS to auth.asrax.in (matches live Keycloak tokens)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import tempfile
import urllib.request

CREDS = pathlib.Path.home() / ".asrax" / "credentials.env"
PATH = "secret/prod/services/am-identity"
ISSUER = "https://auth.asrax.in/auth/realms/am-realm"
# Pod Python image fails TLS verify against the public cert; HTTP JWKS works in-cluster.
JWKS = "http://auth.asrax.in/auth/realms/am-realm/protocol/openid-connect/certs"


def load_vault_env() -> None:
    import os

    for line in CREDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() in ("VAULT_ADDR", "VAULT_TOKEN"):
            os.environ[k.strip()] = v.strip().strip('"')


def main() -> None:
    import os

    load_vault_env()
    existing = subprocess.check_output(
        ["vault", "kv", "get", "-format=json", PATH], text=True
    )
    data = json.loads(existing)["data"]["data"]
    before_iss = data.get("OIDC_ISSUER", "")
    data["OIDC_ISSUER"] = ISSUER
    data["OIDC_JWKS_URL"] = JWKS
    # keep discovery/token urls aligned if present
    if "OIDC_DISCOVERY_URL" in data:
        data["OIDC_DISCOVERY_URL"] = (
            "https://auth.asrax.in/auth/realms/am-realm/.well-known/openid-configuration"
        )
    if "OIDC_TOKEN_URL" in data:
        data["OIDC_TOKEN_URL"] = (
            "https://auth.asrax.in/auth/realms/am-realm/protocol/openid-connect/token"
        )
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(data, f)
        tmp = f.name
    try:
        subprocess.check_call(["vault", "kv", "put", PATH, f"@{tmp}"])
    finally:
        pathlib.Path(tmp).unlink(missing_ok=True)
    print("OK patched", PATH)
    print("OIDC_ISSUER before host:", before_iss.split("/")[2] if before_iss.startswith("http") else before_iss[:40])
    print("OIDC_ISSUER after host: auth.asrax.in")
    # restart user-platform to reload injector env
    subprocess.check_call(
        [
            "kubectl",
            "--kubeconfig",
            str(pathlib.Path.home() / ".asrax" / "kubeconfig.vps"),
            "--context",
            "kind-am-preprod",
            "-n",
            "am-apps-prod",
            "rollout",
            "restart",
            "deploy/am-user-platform",
        ]
    )
    subprocess.check_call(
        [
            "kubectl",
            "--kubeconfig",
            str(pathlib.Path.home() / ".asrax" / "kubeconfig.vps"),
            "--context",
            "kind-am-preprod",
            "-n",
            "am-apps-prod",
            "rollout",
            "status",
            "deploy/am-user-platform",
            "--timeout=180s",
        ]
    )
    print("OK rollout complete")


if __name__ == "__main__":
    main()
