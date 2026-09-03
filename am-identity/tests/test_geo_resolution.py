from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import Request

from am_identity.services.geo_resolution import GeoIpResolver, _geo_from_headers


def test_geo_from_cloudflare_headers() -> None:
    geo = _geo_from_headers(
        {
            "CF-IPCountry": "IN",
            "CF-IPCity": "Mumbai",
        }
    )
    assert geo is not None
    assert geo.city == "Mumbai"
    assert geo.country == "India"


def test_geo_resolver_uses_ip_lookup_when_city_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver = GeoIpResolver()

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, object]:
            return {"success": True, "country": "India", "city": "Pune"}

    fake_client = MagicMock()
    fake_client.__enter__.return_value.get.return_value = FakeResponse()
    monkeypatch.setattr("am_identity.services.geo_resolution.httpx.Client", lambda **_kwargs: fake_client)

    scope = {
        "type": "http",
        "headers": [
            (b"cf-connecting-ip", b"8.8.8.8"),
            (b"cf-ipcountry", b"IN"),
        ],
        "client": ("127.0.0.1", 0),
    }
    request = Request(scope)
    geo = resolver.resolve(request)
    assert geo.city == "Pune"
    assert geo.country == "India"
