from __future__ import annotations

import re

_MOBILE_UA = re.compile(
    r"(android|iphone|ipad|ipod|webos|blackberry|iemobile|opera mini|okhttp)",
    re.IGNORECASE,
)


def is_mobile_user_agent(user_agent: str | None) -> bool:
    if not user_agent or not user_agent.strip():
        return False
    return bool(_MOBILE_UA.search(user_agent))


def is_web_user_agent(user_agent: str | None) -> bool:
    return not is_mobile_user_agent(user_agent)


def parse_os_family(user_agent: str | None) -> str:
    if not user_agent:
        return "unknown"
    ua = user_agent.lower()
    if "windows" in ua:
        return "Windows"
    if "mac os" in ua or "macintosh" in ua:
        return "macOS"
    if "android" in ua:
        return "Android"
    if "iphone" in ua or "ipad" in ua:
        return "iOS"
    if "linux" in ua:
        return "Linux"
    return "unknown"


def device_class_from_user_agent(user_agent: str | None) -> str:
    if not user_agent:
        return "desktop"
    ua = user_agent.lower()
    if any(token in ua for token in ("android", "iphone", "ipod", "mobile")):
        return "mobile"
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    return "desktop"
