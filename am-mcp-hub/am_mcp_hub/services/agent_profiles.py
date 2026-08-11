"""Agent profile packs + bindings under ~/.asrax (laptop-local only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services import laptop_catalog as catalog
from am_mcp_hub.services.catalog_write import CatalogWriteError, _atomic_write, _ensure_under, _write_home

_PRIVACY = "laptop-local"
_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")

_BUILTIN_SEEDS: dict[str, dict[str, Any]] = {
    "developer": {
        "id": "developer",
        "label": "Developer",
        "description": "Org role: feature / API / stack work",
        "skills": [
            "am-service-api",
            "am-repo-structure",
            "am-vault-mappings",
            "amctl",
            "am-kafka",
            "am-temporal",
        ],
        "tools": ["github", "vault", "asrax"],
        "rules_mode": "catalog",
        "model_hint": "small",
        "agents_default": ["api-contract", "reviewer", "test-author"],
        "task_keywords": ["am-service", "openapi", "pull request", "code review", "vault-mappings", "kafka", "bugfix", "api-contract"],
    },
    "dev": {
        "id": "dev",
        "label": "Developer",
        "description": "Alias of developer (legacy id)",
        "skills": [
            "am-service-api",
            "am-repo-structure",
            "am-vault-mappings",
            "amctl",
            "am-kafka",
            "am-temporal",
        ],
        "tools": ["github", "vault", "asrax"],
        "rules_mode": "catalog",
        "model_hint": "small",
        "agents_default": ["api-contract", "reviewer", "test-author"],
        "task_keywords": ["am-service", "openapi", "pull request", "code review", "vault-mappings", "kafka"],
    },
    "qa": {
        "id": "qa",
        "label": "QA",
        "description": "Org role: specs, SPT, verification",
        "skills": ["am-code-review", "am-mcp"],
        "tools": ["am-qa-agent", "github", "asrax"],
        "rules_mode": "catalog",
        "model_hint": "small",
        "agents_default": ["verifier", "test-author", "reviewer"],
        "task_keywords": ["spt", "ui-test", "qa agent", "spec profile", "verify run", "regression"],
    },
    "management": {
        "id": "management",
        "label": "Management",
        "description": "Org role: ops, status, hub / platform oversight",
        "skills": ["am-mcp", "am-admin-web", "amctl"],
        "tools": ["asrax", "argocd", "github"],
        "rules_mode": "catalog",
        "model_hint": "small",
        "agents_default": ["vps-ops", "onboarding"],
        "task_keywords": ["argocd", "vps-ops", "deploy", "incident", "release", "hub status"],
    },
    "admin": {
        "id": "admin",
        "label": "Management",
        "description": "Alias of management (legacy id)",
        "skills": ["am-mcp", "am-admin-web", "amctl", "am-vault-mappings"],
        "tools": ["asrax", "vault", "argocd"],
        "rules_mode": "catalog",
        "model_hint": "small",
        "agents_default": ["vps-ops", "onboarding"],
        "task_keywords": ["argocd", "vps-ops", "hub status", "admin", "vault"],
    },
    "hr": {
        "id": "hr",
        "label": "HR",
        "description": "Org role: hiring, onboarding, people workflows",
        "skills": ["am-chat-memory", "am-mcp"],
        "tools": ["asrax", "google-workspace"],
        "rules_mode": "catalog",
        "model_hint": "small",
        "agents_default": ["onboarding"],
        "task_keywords": ["hiring", "onboard", "resume", "interview", "people ops"],
    },
}

# Default binding when agent has no file and no frontmatter profile.
_DEFAULT_AGENT_BINDINGS: dict[str, dict[str, Any]] = {
    "reviewer": {"profile": "developer"},
    "api-contract": {"profile": "developer"},
    "test-author": {"profile": "developer"},
    "security-scout": {
        "profile": "developer",
        "tools_add": ["vault", "github"],
    },
    "verifier": {"profile": "qa"},
    "vps-ops": {"profile": "management"},
    "onboarding": {
        "profile": "hr",
        "skills_add": ["am-chat-memory"],
        "tools_drop": ["argocd", "vault"],
    },
}


def _profiles_dir(settings: HubSettings) -> Path:
    return _write_home(settings) / "profiles"


def _bindings_dir(settings: HubSettings) -> Path:
    return _write_home(settings) / "agent-bindings"


def _effective_dir(settings: HubSettings) -> Path:
    return _write_home(settings) / "effective"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _known_tool_slugs(settings: HubSettings) -> set[str]:
    known = {
        "asrax",
        "github",
        "vault",
        "google-workspace",
        "argocd",
        "am-qa-agent",
        "am-tool-agent",
        "am-support-agent",
        "am-mcp-server",
        "am-fin-agent",
        "am-engage",
        "grafana",
        "prometheus",
        "keycloak",
        "kafka",
        "litellm",
        "temporal",
        "minio",
        "postman",
        "growthbook",
    }
    home = _write_home(settings)
    bin_dir = home / "bin"
    if bin_dir.is_dir():
        for p in bin_dir.glob("*-mcp.cmd"):
            known.add(p.name[: -len("-mcp.cmd")])
        for p in bin_dir.glob("*-mcp.ps1"):
            known.add(p.name[: -len("-mcp.ps1")])
    return known


def _normalize_profile(raw: dict[str, Any], *, profile_id: str) -> dict[str, Any]:
    skills = raw.get("skills") if isinstance(raw.get("skills"), list) else []
    tools = raw.get("tools") if isinstance(raw.get("tools"), list) else []
    agents_default = raw.get("agents_default") if isinstance(raw.get("agents_default"), list) else []
    keywords = raw.get("task_keywords") if isinstance(raw.get("task_keywords"), list) else []
    return {
        "id": str(raw.get("id") or profile_id),
        "label": str(raw.get("label") or profile_id),
        "description": str(raw.get("description") or ""),
        "skills": [str(s) for s in skills],
        "tools": [str(t) for t in tools],
        "rules_mode": str(raw.get("rules_mode") or "catalog"),
        "model_hint": str(raw.get("model_hint") or "small"),
        "agents_default": [str(a) for a in agents_default],
        "task_keywords": [str(k).lower() for k in keywords],
        "privacy": _PRIVACY,
    }


def _annotate_profile(settings: HubSettings, profile: dict[str, Any]) -> dict[str, Any]:
    known_skills = {s["name"] for s in catalog.list_skills(settings)}
    known_tools = _known_tool_slugs(settings)
    skills = list(profile["skills"])
    tools = list(profile["tools"])
    profile["skills"] = [s for s in skills if s in known_skills]
    profile["skills_missing"] = [s for s in skills if s not in known_skills]
    profile["tools"] = [t for t in tools if t in known_tools]
    profile["tools_missing"] = [t for t in tools if t not in known_tools]
    return profile


def _validate_skills(settings: HubSettings, skills: list[str]) -> tuple[list[str], list[str]]:
    known = {s["name"] for s in catalog.list_skills(settings)}
    ok = [s for s in skills if s in known]
    missing = [s for s in skills if s not in known]
    return ok, missing


def ensure_seed_profiles(settings: HubSettings) -> None:
    root = _profiles_dir(settings)
    root.mkdir(parents=True, exist_ok=True)
    for pid, seed in _BUILTIN_SEEDS.items():
        path = root / f"{pid}.json"
        if path.is_file():
            continue
        _atomic_write(path, json.dumps(seed, indent=2) + "\n", force=False)


def list_profiles(settings: HubSettings) -> list[dict[str, Any]]:
    ensure_seed_profiles(settings)
    root = _profiles_dir(settings)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        raw = _read_json(path)
        if raw is None:
            continue
        profile = _normalize_profile(raw, profile_id=path.stem)
        rows.append(_annotate_profile(settings, profile))
    return rows


def get_profile(settings: HubSettings, profile_id: str) -> dict[str, Any] | None:
    want = profile_id.strip()
    if not want or not _NAME_RE.fullmatch(want):
        return None
    ensure_seed_profiles(settings)
    path = _profiles_dir(settings) / f"{want}.json"
    raw = _read_json(path)
    if raw is None:
        return None
    profile = _normalize_profile(raw, profile_id=want)
    return _annotate_profile(settings, profile)


def put_profile(settings: HubSettings, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    want = profile_id.strip()
    if not want or not _NAME_RE.fullmatch(want):
        raise CatalogWriteError(
            code="validation",
            detail=f"Invalid profile id: {profile_id!r}",
            http_status=400,
        )
    root = _profiles_dir(settings)
    root.mkdir(parents=True, exist_ok=True)
    path = _ensure_under(root, root / f"{want}.json")
    normalized = _normalize_profile({**payload, "id": want}, profile_id=want)
    _atomic_write(
        path,
        json.dumps(
            {k: v for k, v in normalized.items() if k not in {"privacy", "skills_missing", "tools_missing"}},
            indent=2,
        )
        + "\n",
        force=True,
    )
    got = get_profile(settings, want)
    assert got is not None
    return got


def _normalize_binding(raw: dict[str, Any], *, agent: str) -> dict[str, Any]:
    def _list(key: str) -> list[str]:
        val = raw.get(key)
        if not isinstance(val, list):
            return []
        return [str(x) for x in val]

    return {
        "agent": str(raw.get("agent") or agent),
        "profile": str(raw.get("profile") or ""),
        "skills_add": _list("skills_add"),
        "skills_drop": _list("skills_drop"),
        "tools_add": _list("tools_add"),
        "tools_drop": _list("tools_drop"),
        "rules_mode": str(raw.get("rules_mode") or "inherit"),
        "notes": str(raw.get("notes") or ""),
        "privacy": _PRIVACY,
    }


def get_binding(settings: HubSettings, agent: str) -> dict[str, Any] | None:
    want = agent.strip()
    if not want or not _NAME_RE.fullmatch(want):
        return None
    path = _bindings_dir(settings) / f"{want}.json"
    raw = _read_json(path)
    if raw is None:
        return None
    return _normalize_binding(raw, agent=want)


def put_binding(settings: HubSettings, agent: str, payload: dict[str, Any]) -> dict[str, Any]:
    want = agent.strip()
    if not want or not _NAME_RE.fullmatch(want):
        raise CatalogWriteError(
            code="validation",
            detail=f"Invalid agent name: {agent!r}",
            http_status=400,
        )
    root = _bindings_dir(settings)
    root.mkdir(parents=True, exist_ok=True)
    path = _ensure_under(root, root / f"{want}.json")
    normalized = _normalize_binding({**payload, "agent": want}, agent=want)
    _atomic_write(
        path,
        json.dumps({k: v for k, v in normalized.items() if k != "privacy"}, indent=2) + "\n",
        force=True,
    )
    return normalized


def seed_bindings(settings: HubSettings, *, force: bool = False) -> dict[str, Any]:
    """Create missing agent bindings from frontmatter + defaults. Never overwrite unless force."""
    ensure_seed_profiles(settings)
    agents = catalog.list_agents(settings)
    created: list[str] = []
    skipped: list[str] = []
    updated: list[str] = []
    for row in agents:
        name = str(row.get("name") or row.get("rel") or "").replace(".md", "").strip()
        if not name or not _NAME_RE.fullmatch(name):
            continue
        existing = get_binding(settings, name)
        if existing is not None and existing.get("profile") and not force:
            skipped.append(name)
            continue
        hint = str(row.get("profile_hint") or "").strip()
        defaults = dict(_DEFAULT_AGENT_BINDINGS.get(name) or {})
        profile = hint or str(defaults.get("profile") or "")
        if not profile:
            skipped.append(name)
            continue
        payload = {
            "agent": name,
            "profile": profile,
            "skills_add": list(defaults.get("skills_add") or []),
            "skills_drop": list(defaults.get("skills_drop") or []),
            "tools_add": list(defaults.get("tools_add") or []),
            "tools_drop": list(defaults.get("tools_drop") or []),
            "rules_mode": "inherit",
            "notes": "seeded from catalog defaults",
        }
        if existing is not None and force:
            put_binding(settings, name, payload)
            updated.append(name)
        elif existing is None:
            put_binding(settings, name, payload)
            created.append(name)
        elif not existing.get("profile"):
            put_binding(settings, name, {**existing, **payload, "notes": existing.get("notes") or payload["notes"]})
            updated.append(name)
        else:
            skipped.append(name)
    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "privacy": _PRIVACY,
    }


def resolve_effective(settings: HubSettings, agent: str) -> dict[str, Any]:
    want = agent.strip()
    if not want or not _NAME_RE.fullmatch(want):
        raise CatalogWriteError(code="validation", detail=f"Invalid agent: {agent!r}", http_status=400)
    binding = get_binding(settings, want) or _normalize_binding({"agent": want}, agent=want)
    profile_id = binding.get("profile") or ""
    profile = get_profile(settings, profile_id) if profile_id else None
    base_skills = list(profile["skills"]) if profile else []
    base_tools = list(profile["tools"]) if profile else []
    agents_default = list(profile["agents_default"]) if profile else []
    skills = [s for s in base_skills + binding["skills_add"] if s not in binding["skills_drop"]]
    tools = [t for t in base_tools + binding["tools_add"] if t not in binding["tools_drop"]]
    skills = list(dict.fromkeys(skills))
    tools = list(dict.fromkeys(tools))
    ok, missing = _validate_skills(settings, skills)
    known_tools = _known_tool_slugs(settings)
    tools_ok = [t for t in tools if t in known_tools]
    tools_missing = [t for t in tools if t not in known_tools]
    rules_mode = binding["rules_mode"]
    if rules_mode == "inherit":
        rules_mode = (profile or {}).get("rules_mode") or "catalog"
    skill_lines: list[str] = []
    for name in ok:
        got = catalog.get_skill(settings, name)
        desc = ""
        if got and isinstance(got.get("meta"), dict):
            desc = str(got["meta"].get("description") or "")
        elif got:
            desc = str(got.get("body") or "").split("\n", 1)[0][:120]
        skill_lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    tool_lines = [f"- {t}" for t in tools_ok] if tools_ok else ["- (none)"]
    agent_lines = [f"- {a}" for a in agents_default] if agents_default else ["- (none)"]
    brief = "\n".join(
        [
            f"# Effective brief: {want}",
            "",
            f"Profile: {profile_id or '(none)'} (role pack)",
            f"Rules mode: {rules_mode}",
            f"Model hint (docs only): {(profile or {}).get('model_hint') or 'small'}",
            "",
            "## Skills",
            *(skill_lines or ["- (none)"]),
            "",
            "## Allowed MCP tools / servers",
            *tool_lines,
            "",
            "## Preferred sub-agents",
            *agent_lines,
            "",
            "Before other skills, follow this effective brief.",
            "",
        ]
    )
    return {
        "agent": want,
        "profile": profile_id or None,
        "binding": binding,
        "skills": ok,
        "skills_missing": missing,
        "tools": tools_ok,
        "tools_missing": tools_missing,
        "agents_default": agents_default,
        "rules_mode": rules_mode,
        "model_hint": (profile or {}).get("model_hint") or "small",
        "brief": brief,
        "privacy": _PRIVACY,
    }


_BRIEF_MARKER_START = "<!-- am-effective-brief:start -->"
_BRIEF_MARKER_END = "<!-- am-effective-brief:end -->"


def _host_asrax_display_path(path: Path) -> str:
    """Prefer ~/.asrax/... so Cursor on the host can open briefs (not /laptop-asrax)."""
    text = str(path).replace("\\", "/")
    for marker in ("/laptop-asrax/", "/.asrax/"):
        if marker in text:
            rest = text.split(marker, 1)[1]
            return f"~/.asrax/{rest}"
    return str(path)


def _inject_brief_preamble(body: str, brief_display: str) -> str:
    block = (
        f"{_BRIEF_MARKER_START}\n"
        f"Before other skills, follow the effective brief at `{brief_display}`.\n"
        f"{_BRIEF_MARKER_END}\n\n"
    )
    start = body.find(_BRIEF_MARKER_START)
    end = body.find(_BRIEF_MARKER_END)
    if start != -1 and end != -1 and end > start:
        end = end + len(_BRIEF_MARKER_END)
        while end < len(body) and body[end] in "\r\n":
            end += 1
        body = body[:start] + body[end:]
    if body.startswith("---"):
        fm_end = body.find("\n---", 3)
        if fm_end != -1:
            fm_end = fm_end + len("\n---")
            return body[:fm_end] + "\n\n" + block + body[fm_end:].lstrip("\n")
    return block + body


def apply_effective(settings: HubSettings, agent: str) -> dict[str, Any]:
    resolved = resolve_effective(settings, agent)
    home = _write_home(settings)
    eff_dir = home / "effective"
    eff_dir.mkdir(parents=True, exist_ok=True)
    brief_path = _ensure_under(eff_dir, eff_dir / f"{agent}.md")
    _atomic_write(brief_path, resolved["brief"], force=True)
    host_hint = _host_asrax_display_path(brief_path)

    applied: list[str] = [f"wrote {brief_path}"]
    skipped: list[str] = []
    agent_got = catalog.get_agent(settings, agent)
    if agent_got is None:
        skipped.append(f"agent markdown not found for {agent}; brief only")
    else:
        agents_root = home / "agents"
        agents_root.mkdir(parents=True, exist_ok=True)
        # Always patch under write home (~/.asrax); catalog may still resolve legacy ~/.am
        src = Path(str(agent_got["path"]))
        path = _ensure_under(agents_root, agents_root / src.name)
        body = str(agent_got.get("body") or agent_got.get("content") or "")
        if path.resolve() != src.resolve() and path.is_file():
            body = path.read_text(encoding="utf-8")
        body = _inject_brief_preamble(body, host_hint)
        _atomic_write(path, body if body.endswith("\n") else body + "\n", force=True)
        applied.append(f"patched agent preamble: {path}")
        catalog.clear_list_cache()

    rules_mode = resolved["rules_mode"]
    if rules_mode == "override_off":
        rules_dir = home / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        override = rules_dir / "zz-profile-override.mdc"
        text = (
            "---\n"
            "description: Soft profile override (prefer effective brief)\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"Prefer the effective brief at `{host_hint}` over broader catalog rules for this session.\n"
            "Do not delete core alwaysApply rules.\n"
        )
        _atomic_write(override, text, force=True)
        applied.append(f"wrote soft override {override}")
    else:
        skipped.append("rules_mode is not override_off; no zz-profile-override.mdc")

    return {
        "ok": True,
        "agent": agent,
        "brief_path": str(brief_path),
        "host_path_hint": host_hint,
        "applied": applied,
        "skipped": skipped,
        "next_steps": [
            "Reload Cursor window or reopen the agent chat",
            f"Open or @-mention the brief: {host_hint}",
        ],
        "effective": resolved,
        "privacy": _PRIVACY,
    }


def _slim_mcp_catalog(settings: HubSettings) -> list[dict[str, str]]:
    """Launcher/slug list only — no marketplace probe / inspect report."""
    by: dict[str, dict[str, str]] = {}
    for name in ("asrax", "github", "vault", "google-workspace", "argocd"):
        by[name] = {"id": name, "label": name, "description": "core"}
    for row in catalog.list_mcp_launchers(settings):
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        by.setdefault(
            name,
            {
                "id": name,
                "label": name,
                "description": str(row.get("kind") or "launcher"),
            },
        )
    return [by[k] for k in sorted(by)]


def build_agents_bootstrap(settings: HubSettings) -> dict[str, Any]:
    """Single payload for Agents UI first paint (avoids N+1 client fetches)."""
    ensure_seed_profiles(settings)
    agents = catalog.list_agents(settings)
    skills = [
        {
            "id": s["name"],
            "label": s["name"] + (f" · {s['owner']}" if s.get("owner") else ""),
            "description": str(s.get("description") or "")[:90],
        }
        for s in catalog.list_skills(settings)
    ]
    rules = [
        {
            "id": r.get("rel") or r.get("name"),
            "label": r.get("rel") or r.get("name"),
            "always_apply": r.get("always_apply") is True,
        }
        for r in catalog.list_rules(settings)
    ]
    from am_mcp_hub.services import mcp_env_access

    return {
        "agents": agents,
        "profiles": list_profiles(settings),
        "skills": skills,
        "rules": rules,
        "mcp": _slim_mcp_catalog(settings),
        "mcp_env_access": mcp_env_access.read_access(settings),
        "privacy": _PRIVACY,
    }


def build_agent_workspace(settings: HubSettings, agent: str) -> dict[str, Any]:
    """Agent detail + binding + effective in one round-trip."""
    want = agent.strip()
    if not want or not _NAME_RE.fullmatch(want):
        raise CatalogWriteError(code="validation", detail=f"Invalid agent: {agent!r}", http_status=400)
    meta = catalog.get_agent(settings, want)
    binding = get_binding(settings, want) or _normalize_binding({"agent": want}, agent=want)
    if not binding.get("profile") and meta:
        hint = ""
        if isinstance(meta.get("meta"), dict):
            hint = str(meta["meta"].get("profile") or "")
        hint = hint or str(meta.get("profile_hint") or "")
        if hint:
            binding = {**binding, "profile": hint}
    effective = resolve_effective(settings, want)
    return {
        "agent": meta,
        "binding": binding,
        "effective": effective,
        "privacy": _PRIVACY,
    }
