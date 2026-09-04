"""Build IDE system prompts from laptop catalog (skills / rules / agents)."""

from __future__ import annotations

from typing import Any

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services import agent_profiles as profiles
from am_mcp_hub.services import laptop_catalog as catalog
from am_mcp_hub.services.catalog_write import CatalogWriteError

_MAX_RULE_CHARS = 4_000
_MAX_SKILL_CHARS = 8_000
_MAX_RULES = 25
_MAX_SKILLS = 12


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n…(truncated)"


def enrich_catalog_entries(settings: HubSettings, data: dict[str, Any]) -> dict[str, Any]:
    """Attach truncated bodies to bootstrap catalog entries."""
    skills_out: list[dict[str, Any]] = []
    for item in list(data.get("skills") or [])[:50]:
        sid = str(item.get("id") or item.get("name") or "").strip()
        if not sid:
            continue
        got = catalog.get_skill(settings, sid) or {}
        skills_out.append(
            {
                "id": sid,
                "label": str(item.get("label") or sid),
                "description": str(item.get("description") or got.get("meta", {}).get("description") or "")[
                    :200
                ],
                "body": _clip(str(got.get("body") or ""), _MAX_SKILL_CHARS),
            }
        )

    rules_out: list[dict[str, Any]] = []
    for item in list(data.get("rules") or [])[:50]:
        rid = str(item.get("id") or item.get("rel") or item.get("name") or "").strip()
        if not rid:
            continue
        got = catalog.get_rule(settings, rid) or {}
        always = item.get("always_apply")
        if always is None:
            always = got.get("always_apply")
        rules_out.append(
            {
                "id": rid,
                "label": str(item.get("label") or rid),
                "always_apply": always is True,
                "body": _clip(str(got.get("body") or ""), _MAX_RULE_CHARS),
            }
        )

    return {
        "version": "asrax-local",
        "skills": skills_out,
        "rules": rules_out,
        "commands": list(data.get("commands") or []),
    }


def _agent_skill_ids(settings: HubSettings, agent_id: str | None) -> list[str]:
    if not agent_id:
        return []
    try:
        resolved = profiles.resolve_effective(settings, agent_id)
    except CatalogWriteError:
        return []
    if not isinstance(resolved, dict):
        return []
    return [str(s) for s in (resolved.get("skills") or []) if str(s).strip()]


def build_ide_system_prompt(
    settings: HubSettings | None = None,
    *,
    agent_id: str | None = None,
) -> str:
    settings = settings or get_settings()
    parts: list[str] = [
        "You are AM Code, the Asrax coding assistant.",
        "Follow always-apply rules. Use listed skills when relevant.",
        "Prefer Hub MCP tools for external systems. Mutating tools require user approval on the client.",
        "When proposing file edits, return a fenced code block with the full file contents when possible.",
    ]
    if agent_id:
        parts.append(f"Active agent: {agent_id}")

    rules = catalog.list_rules(settings)
    always = [r for r in rules if r.get("always_apply") is True][:_MAX_RULES]
    if always:
        parts.append("## Always-apply rules")
        for r in always:
            rid = str(r.get("rel") or r.get("name") or "rule")
            got = catalog.get_rule(settings, rid) or {}
            body = _clip(str(got.get("body") or r.get("body") or ""), _MAX_RULE_CHARS)
            if body:
                parts.append(f"### {rid}\n{body}")

    skill_ids = _agent_skill_ids(settings, agent_id)
    if not skill_ids:
        skill_ids = [str(s.get("name") or "") for s in catalog.list_skills(settings)[:_MAX_SKILLS]]
    skill_ids = [s for s in skill_ids if s][:_MAX_SKILLS]
    if skill_ids:
        parts.append("## Skills")
        for sid in skill_ids:
            got = catalog.get_skill(settings, sid) or {}
            body = _clip(str(got.get("body") or ""), _MAX_SKILL_CHARS)
            desc = str((got.get("meta") or {}).get("description") or got.get("description") or "")[:200]
            if body:
                parts.append(f"### {sid}\n{body}")
            elif desc:
                parts.append(f"### {sid}\n{desc}")

    return "\n\n".join(parts)
