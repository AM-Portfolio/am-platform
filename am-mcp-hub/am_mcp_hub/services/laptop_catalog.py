"""Read-only laptop catalog (~/.asrax / ~/.am) for hub MCP tools + resources."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from am_mcp_hub.core.config import HubSettings

_FRONTMATTER = re.compile(r"(?s)^---\s*\n(.*?)\n---\s*\n(.*)$")
_LIST_HEAD = 4096
_CACHE_TTL_SEC = 15.0
_T = TypeVar("_T")

_list_cache: dict[str, tuple[float, tuple[Any, ...], Any]] = {}


def _mtime_of(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _tags_from_meta(meta: dict[str, str]) -> list[str]:
    raw = meta.get("tags") or ""
    if not raw.strip():
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def _always_apply_from_meta(meta: dict[str, str]) -> bool | None:
    if "alwaysApply" not in meta:
        return None
    return str(meta.get("alwaysApply", "")).lower() in {"true", "1", "yes"}


def _homes(settings: HubSettings) -> list[Path]:
    out: list[Path] = []
    candidates = (
        settings.laptop_asrax_dir,
        settings.laptop_am_dir,
        str(Path.home() / ".asrax"),
        str(Path.home() / ".am"),
    )
    for raw in candidates:
        if not raw or not str(raw).strip():
            continue
        p = Path(raw).expanduser()
        if p.is_dir() and p not in out:
            out.append(p)
    return out


def _primary_home(settings: HubSettings) -> Path | None:
    homes = _homes(settings)
    return homes[0] if homes else None


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        meta[key.strip()] = val.strip().strip("'").strip('"')
    return meta, match.group(2).lstrip("\n")


def _read_text(path: Path, limit: int = 120_000) -> str:
    try:
        data = path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    if len(data) > limit:
        return data[:limit] + "\n\n…(truncated)"
    return data


def _read_head(path: Path, limit: int = _LIST_HEAD) -> str:
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _dir_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _cache_fingerprint(settings: HubSettings, kind: str) -> tuple[Any, ...]:
    parts: list[Any] = [kind]
    for home in _homes(settings):
        parts.append(str(home))
        root = home / kind
        parts.append(_dir_mtime(root) if root.is_dir() else 0.0)
    return tuple(parts)


def _cached_list(settings: HubSettings, kind: str, builder: Callable[[], _T]) -> _T:
    key = kind
    fp = _cache_fingerprint(settings, kind)
    now = time.monotonic()
    hit = _list_cache.get(key)
    if hit is not None:
        expires_at, cached_fp, value = hit
        if expires_at > now and cached_fp == fp:
            return value  # type: ignore[no-any-return]
    value = builder()
    _list_cache[key] = (now + _CACHE_TTL_SEC, fp, value)
    return value


def clear_list_cache() -> None:
    _list_cache.clear()


def _count_skill_dirs(root: Path) -> int:
    if not root.is_dir():
        return 0
    n = 0
    with os.scandir(root) as it:
        for entry in it:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if (Path(entry.path) / "SKILL.md").is_file():
                n += 1
    return n


def _count_files(root: Path, *, suffixes: set[str], recursive: bool) -> int:
    if not root.is_dir():
        return 0
    n = 0
    if recursive:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                n += 1
        return n
    with os.scandir(root) as it:
        for entry in it:
            if not entry.is_file(follow_symlinks=False):
                continue
            name = entry.name
            if name.startswith(".") or name == "__pycache__":
                continue
            lower = name.lower()
            if lower.endswith(".py") or lower.endswith(".md") or lower.endswith(".json") or lower.endswith(
                ".example"
            ):
                n += 1
    return n


def _count_launchers(bin_dir: Path) -> int:
    if not bin_dir.is_dir():
        return 0
    names: set[str] = set()
    for path in bin_dir.glob("*-mcp.cmd"):
        names.add(path.name[: -len("-mcp.cmd")])
    for path in bin_dir.glob("*-mcp.ps1"):
        names.add(path.name[: -len("-mcp.ps1")])
    return len(names)


def catalog_counts(settings: HubSettings) -> dict[str, int]:
    skills = agents = rules = hooks = launchers = 0
    for home in _homes(settings):
        skills += _count_skill_dirs(home / "skills")
        agents += _count_files(home / "agents", suffixes={".md", ".mdc"}, recursive=True)
        rules += _count_files(home / "rules", suffixes={".md", ".mdc"}, recursive=True)
        hooks += _count_files(home / "hooks", suffixes=set(), recursive=False)
        launchers += _count_launchers(home / "bin")
    return {
        "skills": skills,
        "agents": agents,
        "rules": rules,
        "hooks": hooks,
        "mcp_launchers": launchers,
    }


def catalog_overview(settings: HubSettings) -> dict[str, Any]:
    homes = _homes(settings)
    skills = list_skills(settings)
    agents = list_agents(settings)
    launchers = list_mcp_launchers(settings)
    counts = catalog_counts(settings)
    return {
        "homes": [str(h) for h in homes],
        "counts": counts,
        "skills": [s["name"] for s in skills],
        "agents": [a["name"] for a in agents],
        "mcp_launchers": [m["name"] for m in launchers],
    }


def _list_skills_uncached(settings: HubSettings) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for home in reversed(_homes(settings)):
        root = home / "skills"
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            text = _read_head(skill_md)
            meta, body = _parse_frontmatter(text)
            name = meta.get("name") or skill_dir.name
            by_name[name] = {
                "name": name,
                "path": str(skill_md),
                "home": str(home),
                "description": meta.get("description") or body.split("\n", 1)[0][:300],
                "owner": meta.get("owner"),
                "tags": _tags_from_meta(meta),
                "mtime": _mtime_of(skill_md),
                "uri": f"skill://{name}",
            }
    return [by_name[k] for k in sorted(by_name)]


def list_skills(settings: HubSettings) -> list[dict[str, Any]]:
    return _cached_list(settings, "skills", lambda: _list_skills_uncached(settings))


def _skill_payload(home: Path, skill_md: Path, name: str) -> dict[str, Any]:
    text = _read_text(skill_md)
    meta, body = _parse_frontmatter(text)
    return {
        "name": name,
        "path": str(skill_md),
        "home": str(home),
        "meta": meta,
        "body": body,
        "raw": text,
        "mtime": _mtime_of(skill_md),
        "privacy": "laptop-local",
        "uri": f"skill://{name}",
    }


def get_skill(settings: HubSettings, name: str) -> dict[str, Any] | None:
    want = name.strip()
    if not want or "/" in want or "\\" in want or want in {".", ".."}:
        return None
    for home in reversed(_homes(settings)):
        skill_md = home / "skills" / want / "SKILL.md"
        if skill_md.is_file():
            return _skill_payload(home, skill_md, want)
    for home in reversed(_homes(settings)):
        root = home / "skills"
        if not root.is_dir():
            continue
        for skill_dir in root.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                continue
            head = _read_head(skill_md)
            meta, _ = _parse_frontmatter(head)
            if (meta.get("name") or skill_dir.name) != want:
                continue
            return _skill_payload(home, skill_md, want)
    return None


def _list_agents_uncached(settings: HubSettings) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for home in reversed(_homes(settings)):
        root = home / "agents"
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".mdc"}:
                continue
            rel = path.relative_to(root).as_posix()
            name = path.stem
            text = _read_head(path)
            meta, _ = _parse_frontmatter(text)
            by_name[rel] = {
                "name": name,
                "rel": rel,
                "path": str(path),
                "home": str(home),
                "description": meta.get("description"),
                "owner": meta.get("owner"),
                "readonly": str(meta.get("readonly", "")).lower() in {"true", "1", "yes"},
                "profile_hint": meta.get("profile"),
                "preview": text[:400],
                "mtime": _mtime_of(path),
                "uri": f"agent://{rel}",
            }
    return [by_name[k] for k in sorted(by_name)]


def list_agents(settings: HubSettings) -> list[dict[str, Any]]:
    return _cached_list(settings, "agents", lambda: _list_agents_uncached(settings))


def _agent_payload(home: Path, root: Path, path: Path) -> dict[str, Any]:
    text = _read_text(path)
    meta, _ = _parse_frontmatter(text)
    rel = path.relative_to(root).as_posix()
    item = {
        "name": path.stem,
        "rel": rel,
        "path": str(path),
        "home": str(home),
        "meta": meta,
        "preview": text[:400],
        "mtime": _mtime_of(path),
        "privacy": "laptop-local",
        "uri": f"agent://{rel}",
    }
    return {**item, "content": text, "body": text}


def _under_root(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return path.is_file()
    except (OSError, ValueError):
        return False


def get_agent(settings: HubSettings, name_or_rel: str) -> dict[str, Any] | None:
    want = name_or_rel.strip().replace("\\", "/")
    if not want or ".." in want.split("/"):
        return None
    # Prefer ~/.asrax over legacy ~/.am (same order as _homes / list_agents)
    for home in _homes(settings):
        root = home / "agents"
        if not root.is_dir():
            continue
        candidates = [root / want]
        if not want.endswith((".md", ".mdc")):
            candidates.extend([root / f"{want}.md", root / f"{want}.mdc"])
        for path in candidates:
            if _under_root(root, path):
                return _agent_payload(home, root, path)
        if "/" not in want:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in {".md", ".mdc"}:
                    continue
                if path.stem != want:
                    continue
                return _agent_payload(home, root, path)
    return None


def _list_rules_uncached(settings: HubSettings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for home in reversed(_homes(settings)):
        root = home / "rules"
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".mdc"}:
                continue
            rel = path.relative_to(root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            text = _read_head(path)
            meta, body = _parse_frontmatter(text)
            rows.append(
                {
                    "name": path.stem,
                    "rel": rel,
                    "path": str(path),
                    "home": str(home),
                    "description": meta.get("description")
                    or body.split("\n", 1)[0][:240]
                    or rel,
                    "owner": meta.get("owner"),
                    "always_apply": _always_apply_from_meta(meta),
                    "mtime": _mtime_of(path),
                    "uri": f"rule://{rel}",
                }
            )
    return rows


def list_rules(settings: HubSettings) -> list[dict[str, Any]]:
    return _cached_list(settings, "rules", lambda: _list_rules_uncached(settings))


def get_rule(settings: HubSettings, name_or_rel: str) -> dict[str, Any] | None:
    want = name_or_rel.strip().replace("\\", "/")
    if not want or ".." in want.split("/"):
        return None
    for home in reversed(_homes(settings)):
        root = home / "rules"
        if not root.is_dir():
            continue
        candidates = [root / want]
        if not want.endswith((".md", ".mdc")):
            candidates.extend([root / f"{want}.md", root / f"{want}.mdc"])
        for path in candidates:
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            text = _read_text(path)
            meta, body = _parse_frontmatter(text)
            rel = path.relative_to(root).as_posix()
            return {
                "name": path.stem,
                "rel": rel,
                "path": str(path),
                "home": str(home),
                "description": meta.get("description") or body.split("\n", 1)[0][:240] or rel,
                "uri": f"rule://{rel}",
                "meta": meta,
                "body": body,
                "raw": text,
                "mtime": _mtime_of(path),
                "privacy": "laptop-local",
            }
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".mdc"}:
                continue
            rel = path.relative_to(root).as_posix()
            if rel == want or path.stem == want or rel.endswith("/" + want):
                text = _read_text(path)
                meta, body = _parse_frontmatter(text)
                return {
                    "name": path.stem,
                    "rel": rel,
                    "path": str(path),
                    "home": str(home),
                    "description": meta.get("description")
                    or body.split("\n", 1)[0][:240]
                    or rel,
                    "uri": f"rule://{rel}",
                    "meta": meta,
                    "body": body,
                    "raw": text,
                    "mtime": _mtime_of(path),
                    "privacy": "laptop-local",
                }
    return None


def _hook_file_ok(name: str) -> bool:
    if name.startswith(".") or name == "__pycache__":
        return False
    lower = name.lower()
    return (
        lower.endswith(".py")
        or lower.endswith(".md")
        or lower.endswith(".json")
        or lower.endswith(".example")
        or ".json.example" in lower
    )


def _list_hooks_uncached(settings: HubSettings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for home in reversed(_homes(settings)):
        root = home / "hooks"
        if not root.is_dir():
            continue
        for path in sorted(root.iterdir()):
            if not path.is_file():
                continue
            name = path.name
            if not _hook_file_ok(name) or name in seen:
                continue
            seen.add(name)
            text = _read_head(path)
            preview = next(
                (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")),
                "",
            )
            rows.append(
                {
                    "name": name,
                    "path": str(path),
                    "home": str(home),
                    "kind": path.suffix.lstrip(".") or "file",
                    "description": preview[:240],
                    "mtime": _mtime_of(path),
                    "uri": f"hook://{name}",
                }
            )
    return rows


def list_hooks(settings: HubSettings) -> list[dict[str, Any]]:
    return _cached_list(settings, "hooks", lambda: _list_hooks_uncached(settings))


def get_hook(settings: HubSettings, name: str) -> dict[str, Any] | None:
    want = name.strip()
    if not want or "/" in want or "\\" in want or want in {".", ".."}:
        return None
    for home in reversed(_homes(settings)):
        path = home / "hooks" / want
        if not path.is_file() or not _hook_file_ok(want):
            continue
        text = _read_text(path)
        preview = next(
            (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")),
            "",
        )
        item = {
            "name": want,
            "path": str(path),
            "home": str(home),
            "kind": path.suffix.lstrip(".") or "file",
            "description": preview[:240],
            "mtime": _mtime_of(path),
            "privacy": "laptop-local",
            "uri": f"hook://{want}",
        }
        return {**item, "content": text, "body": text, "raw": text}
    return None


def list_mcp_launchers(settings: HubSettings) -> list[dict[str, Any]]:
    def build() -> list[dict[str, Any]]:
        by_name: dict[str, dict[str, Any]] = {}
        for home in reversed(_homes(settings)):
            bin_dir = home / "bin"
            if not bin_dir.is_dir():
                continue
            for path in sorted(bin_dir.glob("*-mcp.cmd")):
                name = path.name[: -len("-mcp.cmd")]
                by_name[name] = {
                    "name": name,
                    "launcher": path.name,
                    "path": str(path),
                    "home": str(home),
                    "kind": "stdio-launcher",
                    "note": "Runs on host via am ai inspect / Cursor; hub lists metadata in Docker",
                }
            for path in sorted(bin_dir.glob("*-mcp.ps1")):
                name = path.name[: -len("-mcp.ps1")]
                by_name.setdefault(
                    name,
                    {
                        "name": name,
                        "launcher": path.name,
                        "path": str(path),
                        "home": str(home),
                        "kind": "stdio-launcher",
                        "note": "Runs on host via am ai inspect / Cursor; hub lists metadata in Docker",
                    },
                )
        return [by_name[k] for k in sorted(by_name)]

    return _cached_list(settings, "bin", build)


def list_resources(settings: HubSettings) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = [
        {
            "uri": "asrax://catalog/overview",
            "name": "catalog_overview",
            "description": "Skills, agents, rules, MCP launcher counts from mounted asrax homes",
            "mimeType": "application/json",
        }
    ]
    for skill in list_skills(settings):
        resources.append(
            {
                "uri": skill["uri"],
                "name": skill["name"],
                "description": skill.get("description") or f"Skill {skill['name']}",
                "mimeType": "text/markdown",
            }
        )
    for agent in list_agents(settings):
        resources.append(
            {
                "uri": agent["uri"],
                "name": agent["name"],
                "description": f"Agent {agent['rel']}",
                "mimeType": "text/markdown",
            }
        )
    for rule in list_rules(settings):
        resources.append(
            {
                "uri": rule["uri"],
                "name": rule["rel"],
                "description": f"Rule {rule['rel']}",
                "mimeType": "text/markdown",
            }
        )
    return resources


def read_resource(settings: HubSettings, uri: str) -> dict[str, Any] | None:
    uri = uri.strip()
    if uri == "asrax://catalog/overview":
        import json

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(catalog_overview(settings), indent=2),
                }
            ]
        }
    if uri.startswith("skill://"):
        got = get_skill(settings, uri[len("skill://") :])
        if got is None:
            return None
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": got.get("raw") or "",
                }
            ]
        }
    if uri.startswith("agent://"):
        got = get_agent(settings, uri[len("agent://") :])
        if got is None:
            return None
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": got.get("content") or "",
                }
            ]
        }
    if uri.startswith("rule://"):
        got = get_rule(settings, uri[len("rule://") :])
        if got is None:
            return None
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": got.get("raw") or _read_text(Path(got["path"])),
                }
            ]
        }
    return None
