"""Tool adapters: return MCP tool definitions + call handlers. Secrets via env/Vault path metadata only."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from am_mcp_hub.core.config import get_settings
from am_mcp_hub.services import local_creds
from am_mcp_hub.services.catalog import EnabledIntegration

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _tool(
    name: str,
    description: str,
    handler: ToolHandler,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "additionalProperties": True,
        },
        "handler": handler,
    }


async def build_tools(enabled: list[EnabledIntegration]) -> list[dict[str, Any]]:
    settings = get_settings()
    tools: list[dict[str, Any]] = []

    async def hub_status(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": [i.slug for i in enabled],
            "vault_refs": {
                i.slug: ("set" if i.vault_path else "missing") for i in enabled
            },
        }

    tools.append(
        _tool(
            "hub_status",
            "List enabled AM MCP Hub integrations and whether Vault refs are set",
            hub_status,
        )
    )

    from am_mcp_hub.services import laptop_catalog as catalog

    async def catalog_overview(_: dict[str, Any]) -> dict[str, Any]:
        return catalog.catalog_overview(settings)

    async def list_skills(_: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "skills": catalog.list_skills(settings)}

    async def get_skill(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "name is required"}
        got = catalog.get_skill(settings, name)
        if got is None:
            return {"ok": False, "error": f"skill not found: {name}"}
        return {"ok": True, **got}

    async def list_agents(_: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "agents": catalog.list_agents(settings)}

    async def get_agent(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or args.get("rel") or "").strip()
        if not name:
            return {"ok": False, "error": "name or rel is required"}
        got = catalog.get_agent(settings, name)
        if got is None:
            return {"ok": False, "error": f"agent not found: {name}"}
        return {"ok": True, **got}

    async def list_rules(_: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "rules": catalog.list_rules(settings)}

    async def list_mcp_launchers(_: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "launchers": catalog.list_mcp_launchers(settings)}

    tools.extend(
        [
            _tool(
                "catalog_overview",
                "Counts and names for mounted asrax skills, agents, rules, and MCP launchers",
                catalog_overview,
            ),
            _tool(
                "list_skills",
                "List all SKILL.md entries from ~/.asrax and ~/.am (Docker mount)",
                list_skills,
            ),
            _tool(
                "get_skill",
                "Read full skill markdown + frontmatter by name",
                get_skill,
                {"name": {"type": "string", "description": "Skill folder / frontmatter name"}},
            ),
            _tool(
                "list_agents",
                "List agent markdown files from mounted asrax homes",
                list_agents,
            ),
            _tool(
                "get_agent",
                "Read one agent file by name or relative path",
                get_agent,
                {"name": {"type": "string"}, "rel": {"type": "string"}},
            ),
            _tool(
                "list_rules",
                "List Cursor rules (.mdc/.md) from mounted asrax homes",
                list_rules,
            ),
            _tool(
                "list_mcp_launchers",
                "List host *-mcp.cmd / .ps1 launchers (metadata; run on host or via am ai inspect)",
                list_mcp_launchers,
            ),
        ]
    )

    from am_mcp_hub.services import task_queue as tasks

    async def task_list(_: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "tasks": tasks.list_tasks(settings)}

    async def task_get(args: dict[str, Any]) -> dict[str, Any]:
        tid = str(args.get("task_id") or "").strip()
        if not tid:
            return {"ok": False, "error": "task_id is required"}
        try:
            return {"ok": True, "task": tasks.get_task(settings, tid)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def task_claim(args: dict[str, Any]) -> dict[str, Any]:
        tid = str(args.get("task_id") or "").strip()
        phase = str(args.get("phase") or "develop").strip()
        if not tid:
            return {"ok": False, "error": "task_id is required"}
        try:
            return tasks.claim_task(settings, tid, phase=phase)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def task_add_step(args: dict[str, Any]) -> dict[str, Any]:
        tid = str(args.get("task_id") or "").strip()
        title = str(args.get("title") or "").strip()
        if not tid or not title:
            return {"ok": False, "error": "task_id and title are required"}
        ok_raw = args.get("ok")
        ok = None if ok_raw is None else bool(ok_raw)
        try:
            return tasks.add_step(
                settings,
                tid,
                kind=str(args.get("kind") or "note"),
                title=title,
                detail=str(args.get("detail") or ""),
                tool_name=str(args.get("tool_name") or ""),
                ok=ok,
                provider_kind=str(args.get("provider_kind") or "ide"),
            )
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def task_set_analysis(args: dict[str, Any]) -> dict[str, Any]:
        tid = str(args.get("task_id") or "").strip()
        if not tid:
            return {"ok": False, "error": "task_id is required"}
        try:
            return {
                "ok": True,
                "task": tasks.set_analysis(
                    settings,
                    tid,
                    suggested_agent=str(args.get("suggested_agent") or ""),
                    suggested_profile=str(args.get("suggested_profile") or ""),
                    rationale=str(args.get("rationale") or ""),
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def task_complete_phase(args: dict[str, Any]) -> dict[str, Any]:
        tid = str(args.get("task_id") or "").strip()
        phase = str(args.get("phase") or "").strip()
        if not tid or not phase:
            return {"ok": False, "error": "task_id and phase are required"}
        try:
            return {
                "ok": True,
                "task": tasks.complete_phase(
                    settings,
                    tid,
                    phase=phase,
                    ok=bool(args.get("ok", True)),
                    summary=str(args.get("summary") or ""),
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    async def task_complete(args: dict[str, Any]) -> dict[str, Any]:
        tid = str(args.get("task_id") or "").strip()
        if not tid:
            return {"ok": False, "error": "task_id is required"}
        try:
            return {
                "ok": True,
                "task": tasks.complete_task(
                    settings,
                    tid,
                    summary=str(args.get("summary") or ""),
                    ok=bool(args.get("ok", True)),
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)}

    tools.extend(
        [
            _tool("task_list", "List asrax work tasks", task_list),
            _tool(
                "task_get",
                "Get one task by id",
                task_get,
                {"task_id": {"type": "string"}},
            ),
            _tool(
                "task_claim",
                "Claim a task phase for IDE work",
                task_claim,
                {"task_id": {"type": "string"}, "phase": {"type": "string"}},
            ),
            _tool(
                "task_add_step",
                "Append a timeline step (tools/notes/results)",
                task_add_step,
                {
                    "task_id": {"type": "string"},
                    "kind": {"type": "string"},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "tool_name": {"type": "string"},
                    "ok": {"type": "boolean"},
                },
            ),
            _tool(
                "task_set_analysis",
                "Update analysis suggestion on a task",
                task_set_analysis,
                {
                    "task_id": {"type": "string"},
                    "suggested_agent": {"type": "string"},
                    "suggested_profile": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            ),
            _tool(
                "task_complete_phase",
                "Mark analyze/develop/review/test/report phase complete",
                task_complete_phase,
                {
                    "task_id": {"type": "string"},
                    "phase": {"type": "string"},
                    "ok": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
            ),
            _tool(
                "task_complete",
                "Mark entire task done or failed",
                task_complete,
                {
                    "task_id": {"type": "string"},
                    "ok": {"type": "boolean"},
                    "summary": {"type": "string"},
                },
            ),
        ]
    )

    for integ in enabled:
        slug = integ.slug
        if integ.adapter_type == "github":

            async def github_whoami(
                args: dict[str, Any], _slug=slug, _path=integ.vault_path
            ) -> dict[str, Any]:
                token = (args.get("token") or "").strip()
                if not token:
                    token = local_creds.resolve_env_secret(
                        "GITHUB_TOKEN",
                        "GITHUB_PERSONAL_ACCESS_TOKEN",
                    )
                if not token:
                    return {
                        "ok": False,
                        "error": "No GitHub token: set GITHUB_TOKEN in ~/.asrax/credentials.env, pass token in args, or set org vault_path",
                        "vault_path": _path,
                        "integration": _slug,
                    }
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(
                        "https://api.github.com/user",
                        headers={
                            "Authorization": f"Bearer {token}",
                            "Accept": "application/vnd.github+json",
                            "User-Agent": "am-mcp-hub",
                        },
                    )
                    return {"ok": resp.status_code < 300, "status": resp.status_code, "body": resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text}

            tools.append(
                _tool(
                    "github_whoami",
                    "GitHub /user (uses local GITHUB_TOKEN when token arg omitted)",
                    github_whoami,
                    {"token": {"type": "string"}},
                )
            )

        elif integ.adapter_type == "vault":

            async def vault_health(_: dict[str, Any]) -> dict[str, Any]:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(f"{settings.vault_addr.rstrip('/')}/v1/sys/health")
                    return {"ok": resp.status_code < 500, "status": resp.status_code, "body": resp.json()}

            tools.append(
                _tool(
                    "vault_health",
                    f"Vault sys/health against {settings.vault_addr}",
                    vault_health,
                )
            )

        elif integ.adapter_type == "litellm":

            async def litellm_models(
                args: dict[str, Any], _path=integ.vault_path
            ) -> dict[str, Any]:
                key = (args.get("master_key") or "").strip()
                headers = {"Accept": "application/json"}
                if key:
                    headers["Authorization"] = f"Bearer {key}"
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(
                        f"{settings.litellm_url.rstrip('/')}/v1/models",
                        headers=headers,
                    )
                    data: Any
                    try:
                        data = resp.json()
                    except Exception:
                        data = resp.text
                    return {
                        "ok": resp.status_code < 300,
                        "status": resp.status_code,
                        "vault_path": _path,
                        "body": data,
                    }

            tools.append(
                _tool(
                    "litellm_list_models",
                    f"List models from {settings.litellm_url}",
                    litellm_models,
                    {"master_key": {"type": "string"}},
                )
            )

        elif integ.adapter_type == "qa_agent":

            async def qa_health(_: dict[str, Any]) -> dict[str, Any]:
                base = settings.qa_agent_base_url.rstrip("/")
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(f"{base}/health")
                    return {"ok": resp.status_code < 500, "status": resp.status_code, "url": f"{base}/health", "body": resp.text[:2000]}

            tools.append(
                _tool("qa_agent_health", "QA agent health endpoint", qa_health)
            )

        elif integ.adapter_type == "tool_agent":

            async def tool_health(_: dict[str, Any]) -> dict[str, Any]:
                base = settings.tool_agent_base_url.rstrip("/")
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(f"{base}/health")
                    return {"ok": resp.status_code < 500, "status": resp.status_code, "url": f"{base}/health", "body": resp.text[:2000]}

            tools.append(
                _tool("tool_agent_health", "Tool agent health endpoint", tool_health)
            )

        elif integ.adapter_type == "google_workspace":
            from am_mcp_hub.adapters.google_workspace import append_google_workspace_tools

            await append_google_workspace_tools(tools, settings=settings, integ=integ)

    return tools
