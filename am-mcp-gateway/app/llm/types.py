from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMChatResult:
    text: str
    usage: dict[str, int] | None = None
    model: str | None = None


def normalize_usage(raw: dict[str, Any] | None) -> dict[str, int] | None:
    if not raw:
        return None
    mapping = {
        "prompt_tokens": raw.get("prompt_tokens"),
        "completion_tokens": raw.get("completion_tokens"),
        "total_tokens": raw.get("total_tokens"),
    }
    cleaned = {k: int(v) for k, v in mapping.items() if v is not None}
    return cleaned or None
