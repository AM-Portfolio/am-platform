"""Shared helpers for the ai module."""

from __future__ import annotations

TITLE_MAX_LEN = 50
DEFAULT_TITLE = "New chat"


def title_from_first_message(content: str) -> str:
    text = content.strip().replace("\n", " ")
    if not text:
        return DEFAULT_TITLE
    if len(text) <= TITLE_MAX_LEN:
        return text
    return f"{text[: TITLE_MAX_LEN - 1].rstrip()}…"
