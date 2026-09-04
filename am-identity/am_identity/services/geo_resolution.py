from __future__ import annotations

import ipaddress
import threading
import time
from dataclasses import dataclass
from typing import Mapping

import httpx
from fastapi import Request

from am_identity.email.rate_limit import client_ip

_IP_API_FIELDS = "status,country,city"
_IP_API_TIMEOUT_SECONDS = 2.0
_CACHE_TTL_SECONDS = 24 * 60 * 60

_COUNTRY_CODE_NAMES: dict[str, str] = {
    "IN": "India",
    "US": "United States",
    "GB": "United Kingdom",
    "AE": "United Arab Emirates",
    "SG": "Singapore",
    "AU": "Australia",
    "CA": "Canada",
    "DE": "Germany",
    "FR": "France",
}


@dataclass(frozen=True, slots=True)
class GeoLocation:
    city: str | None
    country: str | None


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {name.lower(): value.strip() for name, value in headers.items() if value.strip()}


def _country_label(code: str | None) -> str | None:
    if not code:
        return None
    normalized = code.strip().upper()
    if not normalized or normalized == "XX":
        return None
    return _COUNTRY_CODE_NAMES.get(normalized, normalized)


def _geo_from_headers(headers: Mapping[str, str]) -> GeoLocation | None:
    normalized = _normalized_headers(headers)
    country_code = normalized.get("cf-ipcountry")
    city = normalized.get("cf-ipcity")
    country = _country_label(country_code)
    if city or country:
        return GeoLocation(city=city or None, country=country)
    return None


def _is_lookup_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


class GeoIpResolver:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, GeoLocation]] = {}

    def resolve(self, request: Request) -> GeoLocation:
        header_geo = _geo_from_headers(request.headers)
        ip = client_ip(request)
        if not _is_lookup_ip(ip):
            return header_geo or GeoLocation(city=None, country=None)

        cached = self._cached(ip)
        if cached is not None:
            return self._merge(header_geo, cached)

        looked_up = self._lookup_ip(ip)
        if looked_up is not None:
            self._store(ip, looked_up)
            return self._merge(header_geo, looked_up)

        return header_geo or GeoLocation(city=None, country=None)

    def _merge(self, header_geo: GeoLocation | None, resolved: GeoLocation) -> GeoLocation:
        if header_geo is None:
            return resolved
        return GeoLocation(
            city=header_geo.city or resolved.city,
            country=header_geo.country or resolved.country,
        )

    def _cached(self, ip: str) -> GeoLocation | None:
        now = time.time()
        with self._lock:
            entry = self._cache.get(ip)
            if entry is None:
                return None
            cached_at, geo = entry
            if now - cached_at > _CACHE_TTL_SECONDS:
                del self._cache[ip]
                return None
            return geo

    def _store(self, ip: str, geo: GeoLocation) -> None:
        with self._lock:
            self._cache[ip] = (time.time(), geo)

    def _lookup_ip(self, ip: str) -> GeoLocation | None:
        geo = self._lookup_ipwhois(ip)
        if geo is not None:
            return geo
        return self._lookup_ip_api(ip)

    def _lookup_ipwhois(self, ip: str) -> GeoLocation | None:
        url = f"https://ipwho.is/{ip}"
        try:
            with httpx.Client(timeout=_IP_API_TIMEOUT_SECONDS) as client:
                response = client.get(url)
            if response.status_code != 200:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if payload.get("success") is not True:
            return None
        city = payload.get("city")
        country = payload.get("country")
        return GeoLocation(
            city=city if isinstance(city, str) and city else None,
            country=country if isinstance(country, str) and country else None,
        )

    def _lookup_ip_api(self, ip: str) -> GeoLocation | None:
        url = f"http://ip-api.com/json/{ip}?fields={_IP_API_FIELDS}"
        try:
            with httpx.Client(timeout=_IP_API_TIMEOUT_SECONDS) as client:
                response = client.get(url)
            if response.status_code != 200:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if payload.get("status") != "success":
            return None
        city = payload.get("city")
        country = payload.get("country")
        return GeoLocation(
            city=city if isinstance(city, str) and city else None,
            country=country if isinstance(country, str) and country else None,
        )


geo_ip_resolver = GeoIpResolver()


def geo_from_request(request: Request) -> GeoLocation:
    return geo_ip_resolver.resolve(request)
