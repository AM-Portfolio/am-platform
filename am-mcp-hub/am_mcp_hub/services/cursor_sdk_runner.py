"""Optional local Cursor SDK phase runner (host process)."""

from __future__ import annotations

import os
from typing import Any


def sdk_available() -> bool:
    try:
        import cursor_sdk  # noqa: F401

        return True
    except Exception:
        return False


def run_phase_prompt(
    *,
    prompt: str,
    cwd: str,
    model: str,
    api_key: str,
) -> dict[str, Any]:
    """Run one Cursor local agent turn. Must execute on the host laptop."""
    if not api_key:
        return {"ok": False, "error": "CURSOR_API_KEY missing", "text": ""}
    if not cwd or not os.path.isdir(cwd):
        return {"ok": False, "error": f"cwd missing or not a directory: {cwd}", "text": ""}
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"cursor-sdk not installed: {exc}", "text": ""}

    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model=model or "composer-2.5",
                local=LocalAgentOptions(cwd=cwd),
            ),
        )
        text = str(getattr(result, "result", None) or getattr(result, "text", None) or result or "")
        status = str(getattr(result, "status", "") or "")
        return {"ok": True, "status": status, "text": text[:20000]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:500], "text": ""}
