"""Task pipeline: analyze → develop → review → test → report."""

from __future__ import annotations

import asyncio
from typing import Any

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services import agent_profiles as profiles
from am_mcp_hub.services import task_connections as connections
from am_mcp_hub.services import task_providers as providers
from am_mcp_hub.services import task_queue as queue
from am_mcp_hub.services.catalog_write import CatalogWriteError
from am_mcp_hub.services.cursor_sdk_runner import run_phase_prompt, sdk_available

_KEYWORD_AGENTS: list[tuple[tuple[str, ...], str, str]] = [
    (("test", "pytest", "verify", "regression"), "verifier", "qa"),
    (("review", "pr", "pull request"), "reviewer", "developer"),
    (("security", "vault", "secret", "authz"), "security-scout", "developer"),
    (("openapi", "api contract", "dto"), "api-contract", "developer"),
    (("onboard", "junior", "first week"), "onboarding", "admin"),
    (("k8s", "vps", "kind", "pod"), "vps-ops", "admin"),
]


def analyze_heuristic(settings: HubSettings, task: dict[str, Any]) -> dict[str, str]:
    text = f"{task.get('title') or ''} {task.get('body') or ''}".lower()
    agent = ""
    profile = ""
    for keys, ag, prof in _KEYWORD_AGENTS:
        if any(k in text for k in keys):
            agent, profile = ag, prof
            break
    if not agent:
        if task.get("assignee_type") == "agent":
            agent = str(task.get("assignee_id") or "reviewer")
        else:
            role = str(task.get("assignee_id") or "developer")
            packs = {p["id"]: p for p in profiles.list_profiles(settings)}
            # map org roles
            pack_id = {"developer": "dev", "qa": "qa", "management": "admin", "hr": "hr"}.get(role, role)
            pack = packs.get(pack_id) or packs.get(role) or {}
            defaults = list(pack.get("agents_default") or [])
            agent = defaults[0] if defaults else "reviewer"
            profile = pack_id
    if not profile:
        profile = "dev"
    rationale = (
        f"Matched assignee={task.get('assignee_type')}:{task.get('assignee_id')}; "
        f"suggest agent `{agent}` under profile `{profile}`."
    )
    return {"suggested_agent": agent, "suggested_profile": profile, "rationale": rationale}


async def _maybe_llm_analyze(settings: HubSettings, task: dict[str, Any], base: dict[str, str]) -> dict[str, str]:
    conn_id = str(task.get("connection_id") or "")
    conn = connections.get_connection(settings, conn_id) if conn_id else None
    if conn and conn.get("kind") == "ide":
        doc = connections.load_connections(settings)
        for c in doc.get("connections") or []:
            if c.get("kind") in {"openai_compatible", "gemini", "anthropic"} and c.get("last_ok_at"):
                conn = c
                break
        else:
            return base
    if not conn or conn.get("kind") == "ide" or not conn.get("last_ok_at"):
        return base
    try:
        text = await providers.chat(
            settings,
            conn,
            system=(
                "You analyze software tasks for an internal platform. "
                "Reply with 3-6 short lines: goal, risks, suggested agent name, acceptance checks."
            ),
            user=f"Title: {task.get('title')}\n\n{task.get('body')}\n\nHeuristic: {base['rationale']}",
        )
        if text.strip():
            base = dict(base)
            base["rationale"] = text.strip()[:4000]
    except Exception as exc:  # noqa: BLE001
        queue.add_step(
            settings,
            str(task["id"]),
            kind="note",
            title="LLM analyze skipped",
            detail=str(exc)[:300],
            ok=False,
            provider_kind=str(conn.get("kind") or ""),
        )
    return base


def _ide_conn(settings: HubSettings, task: dict[str, Any]) -> dict[str, Any] | None:
    cid = str(task.get("connection_id") or "")
    conn = connections.get_connection(settings, cid) if cid else None
    if conn and conn.get("kind") == "ide":
        return conn
    doc = connections.load_connections(settings)
    for c in doc.get("connections") or []:
        if c.get("kind") == "ide" and c.get("ide") == "cursor":
            return c
    return None


def _phase_prompt(task: dict[str, Any], phase: str) -> str:
    agent = task.get("suggested_agent") or task.get("assignee_id") or "reviewer"
    tid = task["id"]
    common = (
        f"Task id: {tid}\nTitle: {task.get('title')}\n\n{task.get('body')}\n\n"
        f"Analysis:\n{task.get('analyze_rationale')}\n\n"
        f"Use hub MCP at http://127.0.0.1:8130/mcp. "
        f"Call task_add_step for meaningful actions and task_complete_phase "
        f"with task_id={tid} phase={phase} when done.\n"
    )
    if phase == "develop":
        return (
            f"You are implementing this task (prefer agent `{agent}`).\n"
            f"Make the code changes in the workspace. Do not expand scope.\n\n{common}"
        )
    if phase == "review":
        return (
            "You are the reviewer. Review the latest changes for this task. "
            "Report blockers/majors/minors. Do not rewrite features.\n\n" + common
        )
    if phase == "test":
        return (
            "You are the verifier/test-author. Run targeted tests for this task and report pass/fail.\n\n"
            + common
        )
    return common


async def _run_ide_phase(settings: HubSettings, task_id: str, phase: str) -> bool:
    task = queue.get_task_raw(settings, task_id)
    if task.get("cancel_requested"):
        return False
    conn = _ide_conn(settings, task)
    if conn is None:
        queue.add_step(
            settings,
            task_id,
            kind="error",
            title=f"{phase}: no Cursor IDE connection",
            detail="Create/onboard an ide/cursor connection with cwd + CURSOR_API_KEY",
            ok=False,
        )
        return False

    key = connections.resolve_auth(conn)
    cwd = str(conn.get("cwd") or "").strip()
    prompt = _phase_prompt(task, phase)
    queue.add_step(
        settings,
        task_id,
        kind="plan",
        title=f"Start {phase}",
        detail=f"agent={task.get('suggested_agent')} cwd={cwd}",
        connection_id=str(conn.get("id") or ""),
        provider_kind="ide",
    )

    # Prefer in-process SDK when available (host). Else mark awaiting host CLI.
    if sdk_available() and key and cwd:
        result = await asyncio.to_thread(
            run_phase_prompt,
            prompt=prompt,
            cwd=cwd,
            model=str(conn.get("model") or "composer-2.5"),
            api_key=key,
        )
        queue.add_step(
            settings,
            task_id,
            kind="result" if result.get("ok") else "error",
            title=f"Cursor SDK {phase}",
            detail=(result.get("text") or result.get("error") or "")[:4000],
            ok=bool(result.get("ok")),
            tool_name="cursor_sdk.Agent.prompt",
            connection_id=str(conn.get("id") or ""),
            provider_kind="ide",
        )
        queue.complete_phase(
            settings,
            task_id,
            phase=phase,
            ok=bool(result.get("ok")),
            summary=(result.get("text") or result.get("error") or "")[:1000],
        )
        return bool(result.get("ok"))

    cmd = f'am task run-pipeline --task-id {task_id} --phase {phase}'
    queue.mark_awaiting_host(settings, task_id, command=cmd, phase=phase)
    # Write phase prompt file for host runner
    from pathlib import Path

    from am_mcp_hub.services.task_queue import _task_dir

    d = _task_dir(settings, task_id)
    (d / "phases").mkdir(parents=True, exist_ok=True)
    (d / "phases" / f"{phase}.prompt.md").write_text(prompt + "\n", encoding="utf-8")
    return False  # paused for host


async def run_pipeline(settings: HubSettings, task_id: str, *, connection_id: str = "") -> dict[str, Any]:
    task = queue.queue_for_run(settings, task_id, connection_id=connection_id)
    queue.claim_task(settings, task_id, phase="analyze")

    # ANALYZE
    task = queue.get_task_raw(settings, task_id)
    base = analyze_heuristic(settings, task)
    base = await _maybe_llm_analyze(settings, task, base)
    queue.set_analysis(
        settings,
        task_id,
        suggested_agent=base["suggested_agent"],
        suggested_profile=base["suggested_profile"],
        rationale=base["rationale"],
    )
    if task.get("assignee_type") != "agent" and base["suggested_agent"]:
        # keep role assignee; store suggestion only
        pass
    queue.complete_phase(settings, task_id, phase="analyze", ok=True, summary=base["rationale"][:500])

    task = queue.get_task_raw(settings, task_id)
    if task.get("cancel_requested"):
        return queue.cancel_task(settings, task_id)

    # DEVELOP / REVIEW / TEST via IDE
    for phase in ("develop", "review", "test"):
        task = queue.get_task_raw(settings, task_id)
        if task.get("cancel_requested") or task.get("status") in {"failed", "cancelled"}:
            break
        queue.claim_task(settings, task_id, phase=phase)
        ok = await _run_ide_phase(settings, task_id, phase)
        task = queue.get_task_raw(settings, task_id)
        if task.get("awaiting_host"):
            # Stop here; host CLI continues phases then calls continue-pipeline
            return queue.get_task(settings, task_id)
        if not ok or task.get("status") == "failed":
            return queue.get_task(settings, task_id)

    # REPORT
    task = queue.get_task_raw(settings, task_id)
    if task.get("status") not in {"failed", "cancelled"}:
        queue.claim_task(settings, task_id, phase="report")
        queue.write_report(settings, task_id)
        queue.complete_phase(settings, task_id, phase="report", ok=True, summary="Report written")
        return queue.complete_task(
            settings,
            task_id,
            summary="Pipeline finished: analyze → develop → review → test → report",
            ok=True,
        )
    return queue.get_task(settings, task_id)


async def continue_from_host(settings: HubSettings, task_id: str, *, from_phase: str) -> dict[str, Any]:
    """Resume after host finished a phase (or runs remaining phases with SDK)."""
    order = ["develop", "review", "test"]
    try:
        start = order.index(from_phase)
    except ValueError:
        start = 0
    queue.clear_awaiting_host(settings, task_id)

    for phase in order[start:]:
        task = queue.get_task_raw(settings, task_id)
        if task.get("cancel_requested") or task.get("status") == "failed":
            break
        done = any(
            s.get("phase") == phase and s.get("kind") == "result" and s.get("ok") is True
            for s in (task.get("steps") or [])
            if "Phase " + phase in str(s.get("title") or "")
        )
        if done:
            continue
        queue.claim_task(settings, task_id, phase=phase)
        ok = await _run_ide_phase(settings, task_id, phase)
        task = queue.get_task_raw(settings, task_id)
        if task.get("awaiting_host"):
            return queue.get_task(settings, task_id)
        if not ok:
            return queue.get_task(settings, task_id)

    queue.claim_task(settings, task_id, phase="report")
    queue.write_report(settings, task_id)
    queue.complete_phase(settings, task_id, phase="report", ok=True, summary="Report written")
    return queue.complete_task(
        settings,
        task_id,
        summary="Pipeline finished after host continue",
        ok=True,
    )


# In-process job registry for Assign & Run from API
_jobs: dict[str, asyncio.Task[Any]] = {}


def start_pipeline_job(settings: HubSettings, task_id: str, *, connection_id: str = "") -> dict[str, Any]:
    def _sync_job() -> None:
        try:
            asyncio.run(run_pipeline(settings, task_id, connection_id=connection_id))
        except CatalogWriteError as exc:
            queue.add_step(settings, task_id, kind="error", title="Pipeline error", detail=exc.detail, ok=False)
            try:
                queue.complete_task(settings, task_id, summary=exc.detail, ok=False)
            except CatalogWriteError:
                pass
        except Exception as exc:  # noqa: BLE001
            queue.add_step(settings, task_id, kind="error", title="Pipeline crash", detail=str(exc)[:500], ok=False)
            try:
                queue.complete_task(settings, task_id, summary=str(exc)[:500], ok=False)
            except CatalogWriteError:
                pass

    async def _job() -> None:
        await asyncio.to_thread(_sync_job)

    existing = _jobs.get(task_id)
    if existing and not existing.done():
        raise CatalogWriteError(code="conflict", detail="pipeline already running for task", http_status=409)
    task = queue.queue_for_run(settings, task_id, connection_id=connection_id)
    _jobs[task_id] = asyncio.create_task(_job())
    return {"ok": True, "started": True, "task": task, "privacy": "laptop-local"}
