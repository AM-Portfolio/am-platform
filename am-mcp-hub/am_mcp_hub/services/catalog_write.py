"""Write laptop catalog under LAPTOP_ASRAX_DIR only (skills/rules/hooks/agents)."""

from __future__ import annotations

import errno
import os
import re
import time
from pathlib import Path

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services import laptop_catalog as catalog

_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_PRIVACY = "laptop-local"


class CatalogWriteError(Exception):
    def __init__(
        self,
        *,
        code: str,
        detail: str,
        hint: str = "",
        path: str = "",
        http_status: int = 400,
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.hint = hint
        self.path = path
        self.http_status = http_status


def error_body(err: CatalogWriteError) -> dict[str, object]:
    return {
        "ok": False,
        "code": err.code,
        "detail": err.detail,
        "hint": err.hint,
        "path": err.path,
        "privacy": _PRIVACY,
    }


def _after_write(settings: HubSettings) -> None:
    catalog.clear_list_cache()
    try:
        from am_mcp_hub.services import catalog_index as cat_index

        cat_index.rebuild(settings)
    except Exception:
        pass


def _write_home(settings: HubSettings) -> Path:
    candidates = [
        settings.laptop_asrax_dir.strip(),
        str(Path.home() / ".asrax"),
    ]
    for raw in candidates:
        if not raw:
            continue
        home = Path(raw).expanduser()
        if home.is_dir():
            return home
    raise CatalogWriteError(
        code="not_found",
        detail="asrax home missing",
        hint="Set LAPTOP_ASRAX_DIR or create ~/.asrax (ASRAX_LAPTOP_HOME for Docker).",
        http_status=404,
    )


def _validate_basename(name: str, *, label: str) -> str:
    want = name.strip()
    if not want or not _NAME_RE.fullmatch(want) or want in {".", ".."}:
        raise CatalogWriteError(
            code="validation",
            detail=f"Invalid {label}: {name!r}",
            hint="Use letters, digits, dot, underscore, hyphen only.",
            http_status=400,
        )
    return want


def _validate_rel(rel: str, *, label: str) -> str:
    want = rel.strip().replace("\\", "/")
    if not want or want.startswith("/") or ".." in want.split("/"):
        raise CatalogWriteError(
            code="validation",
            detail=f"Invalid {label} path: {rel!r}",
            hint="Use a relative path without ..",
            http_status=400,
        )
    return want


def _ensure_under(root: Path, path: Path) -> Path:
    root_r = root.resolve()
    candidate = path if path.is_absolute() else root / path
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_r)
    except (OSError, ValueError) as exc:
        raise CatalogWriteError(
            code="validation",
            detail="Path escapes asrax root",
            hint="Refuse writes outside LAPTOP_ASRAX_DIR.",
            path=str(path),
            http_status=400,
        ) from exc
    return resolved


def _file_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _is_lock_error(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        win = getattr(exc, "winerror", None)
        if win in {32, 33}:
            return True
    if isinstance(exc, OSError):
        if exc.errno in {errno.EACCES, errno.EPERM, errno.EBUSY}:
            return True
        win = getattr(exc, "winerror", None)
        if win in {32, 33}:
            return True
        msg = str(exc).lower()
        if "used by another process" in msg or "sharing violation" in msg:
            return True
    return False


def _atomic_write(path: Path, text: str, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    attempts = 3 if force else 1
    last: BaseException | None = None
    for i in range(attempts):
        try:
            tmp.write_text(text, encoding="utf-8", newline="\n")
            os.replace(tmp, path)
            return
        except OSError as exc:
            last = exc
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
            if _is_lock_error(exc):
                if i + 1 < attempts:
                    time.sleep(0.05 * (i + 1))
                    continue
                raise CatalogWriteError(
                    code="file_locked",
                    detail=f"{path.name} is open or locked by another program (often the IDE).",
                    hint="Close the file in Cursor/VS Code, or retry with force=true. Force may still fail while the IDE holds a Windows lock through Docker Desktop.",
                    path=str(path),
                    http_status=409,
                ) from exc
            if isinstance(exc, PermissionError) or exc.errno in {errno.EACCES, errno.EPERM}:
                raise CatalogWriteError(
                    code="permission",
                    detail=f"Permission denied writing {path.name}",
                    hint="Remount /laptop-asrax without :ro, or fix host folder ACLs.",
                    path=str(path),
                    http_status=403,
                ) from exc
            raise CatalogWriteError(
                code="io_error",
                detail=str(exc) or "disk write failed",
                hint="Check free space and mount health.",
                path=str(path),
                http_status=500,
            ) from exc
    if last is not None:
        raise CatalogWriteError(
            code="io_error",
            detail=str(last),
            path=str(path),
            http_status=500,
        ) from last


def _check_mtime(path: Path, expected_mtime: float | None, *, force: bool) -> None:
    if force or expected_mtime is None:
        return
    current = _file_mtime(path)
    if current is None:
        return
    if abs(current - float(expected_mtime)) > 0.001:
        raise CatalogWriteError(
            code="conflict_mtime",
            detail="File changed on disk since you loaded it.",
            hint="Reload the item, or Save with Force update (overwrites disk; unsaved IDE edits may be lost).",
            path=str(path),
            http_status=409,
        )


def _attach_mtime(payload: dict[str, object], path: Path) -> dict[str, object]:
    mtime = _file_mtime(path)
    out = dict(payload)
    out["mtime"] = mtime
    out["privacy"] = _PRIVACY
    return out


def _skill_raw(*, name: str, description: str, body: str, owner: str | None) -> str:
    lines = ["---", f"name: {name}", f"description: {description.strip() or name}"]
    if owner and owner.strip():
        lines.append(f"owner: {owner.strip()}")
    lines.append("---")
    lines.append("")
    body_text = body if body.endswith("\n") or not body else body + "\n"
    return "\n".join(lines) + body_text


def create_skill(
    settings: HubSettings,
    *,
    name: str,
    body: str,
    description: str = "",
    owner: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    want = _validate_basename(name, label="skill name")
    home = _write_home(settings)
    root = home / "skills"
    root.mkdir(parents=True, exist_ok=True)
    skill_md = _ensure_under(root, root / want / "SKILL.md")
    if skill_md.is_file() and not force:
        raise CatalogWriteError(
            code="already_exists",
            detail=f"Skill already exists: {want}",
            hint="Use force=true to replace, or pick another name.",
            path=str(skill_md),
            http_status=409,
        )
    text = _skill_raw(name=want, description=description, body=body, owner=owner)
    _atomic_write(skill_md, text, force=force)
    _after_write(settings)
    got = catalog.get_skill(settings, want)
    assert got is not None
    return _attach_mtime(got, skill_md)


def update_skill(
    settings: HubSettings,
    *,
    name: str,
    body: str,
    description: str | None = None,
    owner: str | None = None,
    expected_mtime: float | None = None,
    force: bool = False,
    raw: str | None = None,
) -> dict[str, object]:
    want = _validate_basename(name, label="skill name")
    home = _write_home(settings)
    root = home / "skills"
    skill_md = _ensure_under(root, root / want / "SKILL.md")
    if not skill_md.is_file():
        raise CatalogWriteError(
            code="not_found",
            detail=f"skill not found: {want}",
            path=str(skill_md),
            http_status=404,
        )
    _check_mtime(skill_md, expected_mtime, force=force)
    if raw is not None:
        text = raw if raw.endswith("\n") else raw + "\n"
    else:
        existing = catalog.get_skill(settings, want) or {}
        meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}
        desc = description if description is not None else str(meta.get("description") or want)
        own = owner if owner is not None else meta.get("owner")
        own_s = str(own) if own else None
        text = _skill_raw(name=want, description=desc, body=body, owner=own_s)
    _atomic_write(skill_md, text, force=force)
    _after_write(settings)
    got = catalog.get_skill(settings, want)
    assert got is not None
    return _attach_mtime(got, skill_md)


def delete_skill(
    settings: HubSettings,
    *,
    name: str,
    confirm: bool,
    force: bool = False,
) -> dict[str, object]:
    if not confirm:
        raise CatalogWriteError(
            code="validation",
            detail="Delete requires confirm=1",
            hint="Retry DELETE with ?confirm=1",
            http_status=400,
        )
    want = _validate_basename(name, label="skill name")
    home = _write_home(settings)
    root = home / "skills"
    skill_dir = _ensure_under(root, root / want)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        raise CatalogWriteError(
            code="not_found",
            detail=f"skill not found: {want}",
            path=str(skill_md),
            http_status=404,
        )
    path_str = str(skill_md)
    try:
        skill_md.unlink()
    except OSError as exc:
        if _is_lock_error(exc):
            raise CatalogWriteError(
                code="file_locked",
                detail="SKILL.md is locked by another program.",
                hint="Close the file in the IDE, then retry.",
                path=path_str,
                http_status=409,
            ) from exc
        raise CatalogWriteError(
            code="io_error",
            detail=str(exc),
            path=path_str,
            http_status=500,
        ) from exc

    leftovers = []
    if skill_dir.is_dir():
        leftovers = [p.name for p in skill_dir.iterdir()]
    if leftovers and not force:
        _after_write(settings)
        raise CatalogWriteError(
            code="not_empty",
            detail=f"Removed SKILL.md but folder still has: {', '.join(leftovers)}",
            hint="Remove leftover files manually, or DELETE with force=true&confirm=1 to remove the directory.",
            path=str(skill_dir),
            http_status=409,
        )
    if skill_dir.is_dir():
        try:
            if force:
                for child in skill_dir.rglob("*"):
                    if child.is_file():
                        child.unlink()
                for child in sorted(skill_dir.rglob("*"), reverse=True):
                    if child.is_dir():
                        child.rmdir()
            skill_dir.rmdir()
        except OSError:
            pass
    _after_write(settings)
    return {"ok": True, "deleted": want, "privacy": _PRIVACY}


def create_rule(
    settings: HubSettings,
    *,
    rel: str,
    body: str,
    description: str = "",
    always_apply: bool | None = None,
    globs: str | None = None,
    force: bool = False,
) -> dict[str, object]:
    want = _validate_rel(rel, label="rule")
    if not want.endswith((".md", ".mdc")):
        want = f"{want}.mdc"
    home = _write_home(settings)
    root = home / "rules"
    root.mkdir(parents=True, exist_ok=True)
    path = _ensure_under(root, root / want)
    if path.is_file() and not force:
        raise CatalogWriteError(
            code="already_exists",
            detail=f"Rule already exists: {want}",
            hint="Use force=true to replace.",
            path=str(path),
            http_status=409,
        )
    text = _rule_raw(body=body, description=description, always_apply=always_apply, globs=globs)
    _atomic_write(path, text, force=force)
    _after_write(settings)
    got = catalog.get_rule(settings, want)
    assert got is not None
    return _attach_mtime(got, path)


def _rule_raw(
    *,
    body: str,
    description: str,
    always_apply: bool | None,
    globs: str | None,
    raw: str | None = None,
) -> str:
    if raw is not None:
        return raw if raw.endswith("\n") else raw + "\n"
    if body.lstrip().startswith("---"):
        return body if body.endswith("\n") else body + "\n"
    lines = ["---"]
    if description.strip():
        lines.append(f"description: {description.strip()}")
    if always_apply is not None:
        lines.append(f"alwaysApply: {'true' if always_apply else 'false'}")
    if globs and globs.strip():
        lines.append(f"globs: {globs.strip()}")
    lines.append("---")
    lines.append("")
    body_text = body if body.endswith("\n") or not body else body + "\n"
    return "\n".join(lines) + body_text


def update_rule(
    settings: HubSettings,
    *,
    rel: str,
    body: str,
    description: str | None = None,
    always_apply: bool | None = None,
    globs: str | None = None,
    expected_mtime: float | None = None,
    force: bool = False,
    raw: str | None = None,
) -> dict[str, object]:
    want = _validate_rel(rel, label="rule")
    home = _write_home(settings)
    root = home / "rules"
    existing = catalog.get_rule(settings, want)
    if existing is None:
        raise CatalogWriteError(
            code="not_found",
            detail=f"rule not found: {want}",
            http_status=404,
        )
    path = Path(str(existing["path"]))
    _ensure_under(root, path)
    _check_mtime(path, expected_mtime, force=force)
    meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else {}
    desc = description if description is not None else str(meta.get("description") or "")
    aa = always_apply
    if aa is None and "alwaysApply" in meta:
        aa = str(meta.get("alwaysApply", "")).lower() in {"true", "1", "yes"}
    gl = globs if globs is not None else meta.get("globs")
    gl_s = str(gl) if gl else None
    text = _rule_raw(body=body, description=desc, always_apply=aa, globs=gl_s, raw=raw)
    _atomic_write(path, text, force=force)
    _after_write(settings)
    got = catalog.get_rule(settings, want)
    assert got is not None
    return _attach_mtime(got, path)


def delete_rule(
    settings: HubSettings,
    *,
    rel: str,
    confirm: bool,
) -> dict[str, object]:
    if not confirm:
        raise CatalogWriteError(
            code="validation",
            detail="Delete requires confirm=1",
            hint="Retry DELETE with ?confirm=1",
            http_status=400,
        )
    want = _validate_rel(rel, label="rule")
    home = _write_home(settings)
    root = home / "rules"
    existing = catalog.get_rule(settings, want)
    if existing is None:
        raise CatalogWriteError(code="not_found", detail=f"rule not found: {want}", http_status=404)
    path = Path(str(existing["path"]))
    _ensure_under(root, path)
    try:
        path.unlink()
    except OSError as exc:
        if _is_lock_error(exc):
            raise CatalogWriteError(
                code="file_locked",
                detail="Rule file is locked.",
                hint="Close it in the IDE, then retry.",
                path=str(path),
                http_status=409,
            ) from exc
        raise CatalogWriteError(code="io_error", detail=str(exc), path=str(path), http_status=500) from exc
    _after_write(settings)
    return {"ok": True, "deleted": want, "privacy": _PRIVACY}


def create_hook(
    settings: HubSettings,
    *,
    name: str,
    content: str,
    force: bool = False,
) -> dict[str, object]:
    want = _validate_basename(name, label="hook name")
    if not catalog._hook_file_ok(want):
        raise CatalogWriteError(
            code="validation",
            detail=f"Unsupported hook filename: {want}",
            hint="Use .py, .md, .json, or .example",
            http_status=400,
        )
    home = _write_home(settings)
    root = home / "hooks"
    root.mkdir(parents=True, exist_ok=True)
    path = _ensure_under(root, root / want)
    if path.is_file() and not force:
        raise CatalogWriteError(
            code="already_exists",
            detail=f"Hook already exists: {want}",
            hint="Use force=true to replace.",
            path=str(path),
            http_status=409,
        )
    text = content if content.endswith("\n") else content + "\n"
    _atomic_write(path, text, force=force)
    _after_write(settings)
    got = catalog.get_hook(settings, want)
    assert got is not None
    return _attach_mtime(got, path)


def update_hook(
    settings: HubSettings,
    *,
    name: str,
    content: str,
    expected_mtime: float | None = None,
    force: bool = False,
) -> dict[str, object]:
    want = _validate_basename(name, label="hook name")
    home = _write_home(settings)
    root = home / "hooks"
    path = root / want
    if not path.is_file():
        raise CatalogWriteError(code="not_found", detail=f"hook not found: {want}", http_status=404)
    _ensure_under(root, path)
    _check_mtime(path, expected_mtime, force=force)
    text = content if content.endswith("\n") else content + "\n"
    _atomic_write(path, text, force=force)
    _after_write(settings)
    got = catalog.get_hook(settings, want)
    assert got is not None
    return _attach_mtime(got, path)


def delete_hook(
    settings: HubSettings,
    *,
    name: str,
    confirm: bool,
) -> dict[str, object]:
    if not confirm:
        raise CatalogWriteError(
            code="validation",
            detail="Delete requires confirm=1",
            hint="Retry DELETE with ?confirm=1",
            http_status=400,
        )
    want = _validate_basename(name, label="hook name")
    home = _write_home(settings)
    root = home / "hooks"
    path = root / want
    if not path.is_file():
        raise CatalogWriteError(code="not_found", detail=f"hook not found: {want}", http_status=404)
    _ensure_under(root, path)
    try:
        path.unlink()
    except OSError as exc:
        if _is_lock_error(exc):
            raise CatalogWriteError(
                code="file_locked",
                detail="Hook file is locked.",
                path=str(path),
                http_status=409,
            ) from exc
        raise CatalogWriteError(code="io_error", detail=str(exc), path=str(path), http_status=500) from exc
    _after_write(settings)
    return {"ok": True, "deleted": want, "privacy": _PRIVACY}


def create_agent(
    settings: HubSettings,
    *,
    rel: str,
    body: str,
    force: bool = False,
) -> dict[str, object]:
    want = _validate_rel(rel, label="agent")
    if not want.endswith((".md", ".mdc")):
        want = f"{want}.md"
    home = _write_home(settings)
    root = home / "agents"
    root.mkdir(parents=True, exist_ok=True)
    path = _ensure_under(root, root / want)
    if path.is_file() and not force:
        raise CatalogWriteError(
            code="already_exists",
            detail=f"Agent already exists: {want}",
            hint="Use force=true to replace.",
            path=str(path),
            http_status=409,
        )
    text = body if body.endswith("\n") else body + "\n"
    _atomic_write(path, text, force=force)
    _after_write(settings)
    got = catalog.get_agent(settings, want)
    assert got is not None
    return _attach_mtime(got, path)


def update_agent(
    settings: HubSettings,
    *,
    rel: str,
    body: str,
    expected_mtime: float | None = None,
    force: bool = False,
) -> dict[str, object]:
    want = _validate_rel(rel, label="agent")
    home = _write_home(settings)
    root = home / "agents"
    existing = catalog.get_agent(settings, want)
    if existing is None:
        raise CatalogWriteError(code="not_found", detail=f"agent not found: {want}", http_status=404)
    path = Path(str(existing["path"]))
    _ensure_under(root, path)
    _check_mtime(path, expected_mtime, force=force)
    text = body if body.endswith("\n") else body + "\n"
    _atomic_write(path, text, force=force)
    _after_write(settings)
    got = catalog.get_agent(settings, want)
    assert got is not None
    return _attach_mtime(got, path)


def delete_agent(
    settings: HubSettings,
    *,
    rel: str,
    confirm: bool,
) -> dict[str, object]:
    if not confirm:
        raise CatalogWriteError(
            code="validation",
            detail="Delete requires confirm=1",
            hint="Retry DELETE with ?confirm=1",
            http_status=400,
        )
    want = _validate_rel(rel, label="agent")
    home = _write_home(settings)
    root = home / "agents"
    existing = catalog.get_agent(settings, want)
    if existing is None:
        raise CatalogWriteError(code="not_found", detail=f"agent not found: {want}", http_status=404)
    path = Path(str(existing["path"]))
    _ensure_under(root, path)
    try:
        path.unlink()
    except OSError as exc:
        if _is_lock_error(exc):
            raise CatalogWriteError(
                code="file_locked",
                detail="Agent file is locked.",
                path=str(path),
                http_status=409,
            ) from exc
        raise CatalogWriteError(code="io_error", detail=str(exc), path=str(path), http_status=500) from exc
    _after_write(settings)
    return {"ok": True, "deleted": want, "privacy": _PRIVACY}
