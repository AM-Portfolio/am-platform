"""Laptop-local task queue under LAPTOP_ASRAX_DIR/work/tasks."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.catalog_write import CatalogWriteError, _write_home

_PRIVACY = "laptop-local"
_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_STATUSES = frozenset({"draft", "queued", "running", "done", "failed", "cancelled"})
_PHASES = frozenset({"idle", "analyze", "develop", "review", "test", "report"})
_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"queued", "cancelled"}),
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"done", "failed", "cancelled"}),
    "done": frozenset(),
    "failed": frozenset({"queued", "cancelled"}),
    "cancelled": frozenset({"queued"}),
}
_PHASE_ORDER = ("analyze", "develop", "review", "test", "report")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _work_root(settings: HubSettings) -> Path:
    home = _write_home(settings)
    root = home / "work" / "tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _task_dir(settings: HubSettings, task_id: str) -> Path:
    if not _ID_RE.fullmatch(task_id):
        raise CatalogWriteError(code="validation", detail=f"Invalid task id: {task_id!r}", http_status=400)
    return _work_root(settings) / task_id


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    tmp.replace(path)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(settings: HubSettings, task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task["id"])
    task["updated_at"] = _now()
    task["privacy"] = _PRIVACY
    d = _task_dir(settings, task_id)
    d.mkdir(parents=True, exist_ok=True)
    _atomic_write(d / "task.json", json.dumps(task, indent=2, ensure_ascii=False))
    return task


def _public(task: dict[str, Any]) -> dict[str, Any]:
    out = dict(task)
    out.pop("claim_token", None)
    out["privacy"] = _PRIVACY
    return out


def create_task(
    settings: HubSettings,
    *,
    title: str,
    body: str = "",
    assignee_type: str = "role",
    assignee_id: str = "developer",
    connection_id: str = "",
) -> dict[str, Any]:
    title = (title or "").strip()
    if not title:
        raise CatalogWriteError(code="validation", detail="title is required", http_status=400)
    at = assignee_type if assignee_type in {"role", "agent"} else "role"
    task_id = uuid.uuid4().hex[:12]
    task: dict[str, Any] = {
        "id": task_id,
        "title": title,
        "body": body or "",
        "status": "draft",
        "phase": "idle",
        "assignee_type": at,
        "assignee_id": (assignee_id or "developer").strip(),
        "connection_id": (connection_id or "").strip(),
        "suggested_agent": "",
        "suggested_profile": "",
        "analyze_rationale": "",
        "created_at": _now(),
        "updated_at": _now(),
        "claimed_at": None,
        "completed_at": None,
        "claim_token": None,
        "cancel_requested": False,
        "awaiting_host": False,
        "host_command": "",
        "steps": [],
        "result_summary": "",
        "error": "",
        "report": None,
        "privacy": _PRIVACY,
    }
    _save(settings, task)
    write_brief(settings, task)
    return _public(task)


def list_tasks(settings: HubSettings) -> list[dict[str, Any]]:
    root = _work_root(settings)
    rows: list[dict[str, Any]] = []
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        path = d / "task.json"
        if not path.is_file():
            continue
        try:
            rows.append(_public(_load(path)))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def get_task(settings: HubSettings, task_id: str) -> dict[str, Any]:
    path = _task_dir(settings, task_id) / "task.json"
    if not path.is_file():
        raise CatalogWriteError(code="not_found", detail=f"task not found: {task_id}", http_status=404)
    return _public(_load(path))


def get_task_raw(settings: HubSettings, task_id: str) -> dict[str, Any]:
    path = _task_dir(settings, task_id) / "task.json"
    if not path.is_file():
        raise CatalogWriteError(code="not_found", detail=f"task not found: {task_id}", http_status=404)
    return _load(path)


def _set_status(task: dict[str, Any], new_status: str) -> None:
    cur = str(task.get("status") or "draft")
    if new_status == cur:
        return
    allowed = _TRANSITIONS.get(cur, frozenset())
    if new_status not in allowed:
        raise CatalogWriteError(
            code="conflict",
            detail=f"Cannot transition {cur} -> {new_status}",
            http_status=409,
        )
    task["status"] = new_status


def patch_task(settings: HubSettings, task_id: str, **fields: Any) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    for key in ("title", "body", "assignee_type", "assignee_id", "connection_id"):
        if key in fields and fields[key] is not None:
            task[key] = fields[key]
    if "status" in fields and fields["status"] is not None:
        _set_status(task, str(fields["status"]))
    if "phase" in fields and fields["phase"] is not None:
        phase = str(fields["phase"])
        if phase not in _PHASES:
            raise CatalogWriteError(code="validation", detail=f"invalid phase: {phase}", http_status=400)
        task["phase"] = phase
    _save(settings, task)
    write_brief(settings, task)
    return _public(task)


def add_step(
    settings: HubSettings,
    task_id: str,
    *,
    kind: str,
    title: str,
    detail: str = "",
    tool_name: str = "",
    ok: bool | None = None,
    connection_id: str = "",
    provider_kind: str = "",
) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    step = {
        "id": uuid.uuid4().hex[:10],
        "at": _now(),
        "kind": (kind or "note").strip()[:40],
        "title": (title or "").strip()[:200] or "step",
        "detail": (detail or "")[:8000],
        "tool_name": (tool_name or "")[:120],
        "ok": ok,
        "connection_id": connection_id or task.get("connection_id") or "",
        "provider_kind": provider_kind or "",
        "phase": task.get("phase") or "idle",
    }
    steps = list(task.get("steps") or [])
    steps.append(step)
    task["steps"] = steps
    _save(settings, task)
    return {"ok": True, "step": step, "task": _public(task), "privacy": _PRIVACY}


def claim_task(settings: HubSettings, task_id: str, *, phase: str | None = None) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    if task.get("cancel_requested"):
        raise CatalogWriteError(code="conflict", detail="cancel requested", http_status=409)
    status = str(task.get("status") or "draft")
    if status == "draft":
        _set_status(task, "queued")
        status = "queued"
    if status == "queued":
        _set_status(task, "running")
    elif status != "running":
        raise CatalogWriteError(code="conflict", detail=f"cannot claim from status {status}", http_status=409)
    if task.get("claim_token") and status == "running" and task.get("claimed_at"):
        # allow re-claim only for next phase when token already set by same pipeline
        pass
    else:
        task["claim_token"] = secrets.token_urlsafe(16)
        task["claimed_at"] = _now()
    if phase:
        if phase not in _PHASES:
            raise CatalogWriteError(code="validation", detail=f"invalid phase: {phase}", http_status=400)
        task["phase"] = phase
    _save(settings, task)
    return {"ok": True, "claim_token": task["claim_token"], "task": _public(task), "privacy": _PRIVACY}


def complete_phase(settings: HubSettings, task_id: str, *, phase: str, ok: bool = True, summary: str = "") -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    if str(task.get("phase")) != phase and phase in _PHASES:
        task["phase"] = phase
    add_step(
        settings,
        task_id,
        kind="result" if ok else "error",
        title=f"Phase {phase} {'ok' if ok else 'failed'}",
        detail=summary,
        ok=ok,
    )
    task = get_task_raw(settings, task_id)
    if not ok:
        _set_status(task, "failed")
        task["error"] = summary or f"phase {phase} failed"
        task["phase"] = phase
        _save(settings, task)
        return _public(task)
    try:
        idx = _PHASE_ORDER.index(phase)
    except ValueError:
        idx = -1
    if idx >= 0 and idx + 1 < len(_PHASE_ORDER):
        task["phase"] = _PHASE_ORDER[idx + 1]
    else:
        task["phase"] = "idle"
    _save(settings, task)
    return _public(task)


def complete_task(settings: HubSettings, task_id: str, *, summary: str = "", ok: bool = True) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    _set_status(task, "done" if ok else "failed")
    task["completed_at"] = _now()
    task["result_summary"] = summary or task.get("result_summary") or ""
    if not ok:
        task["error"] = summary or task.get("error") or "failed"
    task["phase"] = "idle"
    task["awaiting_host"] = False
    _save(settings, task)
    return _public(task)


def cancel_task(settings: HubSettings, task_id: str) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    task["cancel_requested"] = True
    try:
        _set_status(task, "cancelled")
    except CatalogWriteError:
        task["status"] = "cancelled"
    task["phase"] = "idle"
    task["awaiting_host"] = False
    _save(settings, task)
    add_step(settings, task_id, kind="note", title="Cancelled", detail="User cancelled pipeline")
    return get_task(settings, task_id)


def set_analysis(
    settings: HubSettings,
    task_id: str,
    *,
    suggested_agent: str = "",
    suggested_profile: str = "",
    rationale: str = "",
) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    if suggested_agent:
        task["suggested_agent"] = suggested_agent.strip()
    if suggested_profile:
        task["suggested_profile"] = suggested_profile.strip()
    if rationale:
        task["analyze_rationale"] = rationale.strip()
    _save(settings, task)
    add_step(
        settings,
        task_id,
        kind="analysis",
        title="Analysis updated",
        detail=rationale or f"agent={suggested_agent} profile={suggested_profile}",
    )
    return get_task(settings, task_id)


def write_brief(settings: HubSettings, task: dict[str, Any]) -> Path:
    d = _task_dir(settings, str(task["id"]))
    d.mkdir(parents=True, exist_ok=True)
    path = d / "brief.md"
    text = (
        f"# Task {task['id']}: {task.get('title')}\n\n"
        f"**Status:** {task.get('status')} · **Phase:** {task.get('phase')}\n\n"
        f"**Assignee:** {task.get('assignee_type')} `{task.get('assignee_id')}`\n\n"
        f"**Suggested agent:** {task.get('suggested_agent') or '—'}  \n"
        f"**Suggested profile:** {task.get('suggested_profile') or '—'}  \n\n"
        f"## Request\n\n{task.get('body') or '(empty)'}\n\n"
        f"## Analysis\n\n{task.get('analyze_rationale') or '(pending)'}\n\n"
        f"## Cursor handoff\n\n"
        f"Use local hub MCP `http://127.0.0.1:8130/mcp` and call `task_add_step` / "
        f"`task_complete_phase` with task_id `{task['id']}`.\n\n"
        f"Command: `/task-run {task['id']}`\n"
    )
    _atomic_write(path, text)
    return path


def write_report(settings: HubSettings, task_id: str) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    steps = list(task.get("steps") or [])
    tools = [s for s in steps if s.get("kind") == "tool" or s.get("tool_name")]
    errors = [s for s in steps if s.get("ok") is False or s.get("kind") == "error"]
    lines = [
        f"# Report: {task.get('title')}",
        "",
        f"- **Task id:** `{task_id}`",
        f"- **Status:** {task.get('status')}",
        f"- **Assignee:** {task.get('assignee_type')} `{task.get('assignee_id')}`",
        f"- **Suggested agent:** {task.get('suggested_agent') or '—'}",
        f"- **Steps:** {len(steps)} · **Tool steps:** {len(tools)} · **Errors:** {len(errors)}",
        "",
        "## Summary",
        "",
        task.get("result_summary") or task.get("analyze_rationale") or "(no summary)",
        "",
        "## Timeline",
        "",
    ]
    for s in steps:
        mark = "ok" if s.get("ok") is True else ("fail" if s.get("ok") is False else "—")
        tool = f" `{s.get('tool_name')}`" if s.get("tool_name") else ""
        lines.append(f"- [{s.get('phase')}] **{s.get('kind')}** {s.get('title')} ({mark}){tool}")
        if s.get("detail"):
            lines.append(f"  - {str(s['detail']).splitlines()[0][:200]}")
    if task.get("error"):
        lines.extend(["", "## Error", "", str(task.get("error"))])
    report_md = "\n".join(lines) + "\n"
    d = _task_dir(settings, task_id)
    _atomic_write(d / "report.md", report_md)
    report = {
        "markdown": report_md,
        "step_count": len(steps),
        "tool_count": len(tools),
        "error_count": len(errors),
        "generated_at": _now(),
    }
    task["report"] = report
    task["result_summary"] = task.get("result_summary") or f"Completed with {len(steps)} steps, {len(errors)} errors"
    _save(settings, task)
    return _public(task)


def queue_for_run(settings: HubSettings, task_id: str, *, connection_id: str = "") -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    if connection_id:
        task["connection_id"] = connection_id.strip()
    if task.get("status") in {"done", "failed", "cancelled"}:
        task["status"] = "draft"
        task["error"] = ""
        task["cancel_requested"] = False
    _set_status(task, "queued")
    task["phase"] = "analyze"
    task["awaiting_host"] = False
    _save(settings, task)
    write_brief(settings, task)
    return _public(task)


def mark_awaiting_host(settings: HubSettings, task_id: str, *, command: str, phase: str) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    task["awaiting_host"] = True
    task["host_command"] = command
    task["phase"] = phase
    if task.get("status") == "queued":
        _set_status(task, "running")
    _save(settings, task)
    add_step(
        settings,
        task_id,
        kind="note",
        title="Awaiting host Cursor runner",
        detail=command,
    )
    return get_task(settings, task_id)


def clear_awaiting_host(settings: HubSettings, task_id: str) -> dict[str, Any]:
    task = get_task_raw(settings, task_id)
    task["awaiting_host"] = False
    _save(settings, task)
    return _public(task)
