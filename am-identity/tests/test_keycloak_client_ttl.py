from pathlib import Path


_TERRAFORM = (
    Path(__file__).resolve().parents[2]
    / "automation"
    / "terraform"
    / "modules"
    / "keycloak"
    / "main.tf"
)


def test_web_client_has_seven_day_session_ttl() -> None:
    content = _TERRAFORM.read_text(encoding="utf-8")
    web_block = content.split('client_id   = "am-web-client"', 1)[1].split(
        'resource "keycloak_openid_client" "am_android_client"', 1
    )[0]
    assert 'client_session_idle_timeout = "168h"' in web_block
    assert 'client_session_max_lifespan = "168h"' in web_block


def test_mobile_clients_have_fifteen_day_session_ttl() -> None:
    content = _TERRAFORM.read_text(encoding="utf-8")
    for marker in ('client_id   = "am-android-client"', 'client_id   = "am-ios-client"'):
        block = content.split(marker, 1)[1].split("resource ", 1)[0]
        assert 'client_session_idle_timeout = "360h"' in block
        assert 'client_session_max_lifespan = "360h"' in block


def test_realm_enables_refresh_token_rotation() -> None:
    content = _TERRAFORM.read_text(encoding="utf-8")
    assert "revoke_refresh_token     = true" in content
