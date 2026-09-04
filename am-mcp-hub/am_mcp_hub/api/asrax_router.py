"""Asrax catalog + chat-memory APIs for hub admin UI (~/.asrax mounts)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from am_mcp_hub.api.ui_schemas import (
    AgentBinding,
    AgentWriteRequest,
    AsraxAgentsListResponse,
    AsraxHooksListResponse,
    AsraxRulesListResponse,
    AsraxSkillsListResponse,
    ChatListResponse,
    ConnectionUpsertRequest,
    HookWriteRequest,
    McpEnvAccessPut,
    ProfilePack,
    ProfilesListResponse,
    RuleWriteRequest,
    SeedBindingsRequest,
    SkillWriteRequest,
    TaskAnalysisRequest,
    TaskAssignRunRequest,
    TaskCompletePhaseRequest,
    TaskCompleteRequest,
    TaskCreateRequest,
    TaskPatchRequest,
    TaskStepRequest,
)
from am_mcp_hub.core.config import get_settings
from am_mcp_hub.services.auth import (
    AuthContext,
    assert_can_write_catalog,
    assert_can_write_env,
    is_platform_admin,
    require_auth,
)
from am_mcp_hub.services import agent_profiles as profiles
from am_mcp_hub.services import catalog_index as cat_index
from am_mcp_hub.services import chat_memory as chat_mem
from am_mcp_hub.services import laptop_catalog as catalog
from am_mcp_hub.services import mcp_env_access
from am_mcp_hub.services.catalog_write import (
    CatalogWriteError,
    create_agent,
    create_hook,
    create_rule,
    create_skill,
    delete_agent,
    delete_hook,
    delete_rule,
    delete_skill,
    error_body,
    update_agent,
    update_hook,
    update_rule,
    update_skill,
)

_routes = APIRouter()


def _require(data: dict | None, detail: str) -> dict:
    if data is None:
        raise HTTPException(status_code=404, detail=detail)
    return data


async def catalog_write_exception_handler(_: Request, exc: CatalogWriteError) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=error_body(exc))


@_routes.get("/chat/sources", summary="Chat memory sources")
async def chat_sources(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    settings = get_settings()
    sources = await asyncio.to_thread(chat_mem.distinct_sources, settings)
    return {
        "chat_memory_root": str(chat_mem.chat_memory_root(settings)),
        "sources": sources,
    }


@_routes.get(
    "/chat/list",
    summary="List chat conversations",
    response_model=ChatListResponse,
    response_model_exclude_none=True,
)
async def chat_list(
    q: str | None = None,
    source: str | None = None,
    profile: str | None = None,
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    include_sources: bool | None = Query(
        None,
        description="Include source chips. Default true when offset=0, false otherwise.",
    ),
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    settings = get_settings()
    want_sources = include_sources if include_sources is not None else offset == 0

    def _load() -> tuple[list, list | None]:
        items = chat_mem.list_conversations(
            settings,
            limit=limit,
            offset=offset,
            source=source,
            profile_id=profile,
            query=q,
        )
        sources = chat_mem.distinct_sources(settings) if want_sources else None
        return items, sources

    items, sources = await asyncio.to_thread(_load)
    out: dict = {
        "chat_memory_root": str(chat_mem.chat_memory_root(settings)),
        "items": items,
        "limit": limit,
        "offset": offset,
    }
    if sources is not None:
        out["sources"] = sources
    return out


@_routes.get("/chat/conversation", summary="Get one chat conversation")
async def chat_conversation(id: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(chat_mem.get_conversation, get_settings(), id)
    return _require(data, "conversation not found")


@_routes.get("/overview", summary="Asrax catalog overview")
async def asrax_overview(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(catalog.catalog_overview, get_settings())


@_routes.get(
    "/skills",
    summary="List skills",
    response_model=AsraxSkillsListResponse,
)
async def skills_list(
    q: str | None = None,
    owner: str | None = None,
    tag: str | None = None,
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    settings = get_settings()
    if q or owner or tag:

        def _indexed() -> list:
            try:
                indexed = cat_index.query(settings, kind="skills", q=q, owner=owner, tag=tag)
            except Exception:
                indexed = []
            if not indexed:
                return catalog.list_skills(settings)
            by_name = {s["name"]: s for s in catalog.list_skills(settings)}
            return [by_name[r["id"]] for r in indexed if r["id"] in by_name]

        skills = await asyncio.to_thread(_indexed)
    else:
        skills = await asyncio.to_thread(catalog.list_skills, settings)
    return {"skills": skills, "privacy": "laptop-local"}


@_routes.get("/skills/{name}", summary="Get skill by name")
async def skills_get(name: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(catalog.get_skill, get_settings(), name)
    return _require(data, f"skill not found: {name}")


@_routes.post("/skills", summary="Create skill under ~/.asrax")
async def skills_create(body: SkillWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    if not body.name:
        raise CatalogWriteError(code="validation", detail="name is required", http_status=400)
    return await asyncio.to_thread(
        create_skill,
        get_settings(),
        name=body.name,
        body=body.body,
        description=body.description or "",
        owner=body.owner,
        force=body.force,
    )


@_routes.put("/skills/{name}", summary="Update skill")
async def skills_update(name: str, body: SkillWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(
        update_skill,
        get_settings(),
        name=name,
        body=body.body,
        description=body.description,
        owner=body.owner,
        expected_mtime=body.expected_mtime,
        force=body.force,
        raw=body.raw,
    )


@_routes.delete("/skills/{name}", summary="Delete skill SKILL.md")
async def skills_delete(
    name: str,
    confirm: int = Query(0),
    force: bool = Query(False),
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    return await asyncio.to_thread(
        delete_skill,
        get_settings(),
        name=name,
        confirm=bool(confirm),
        force=force,
    )


@_routes.get(
    "/rules",
    summary="List rules",
    response_model=AsraxRulesListResponse,
)
async def rules_list(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    rules = await asyncio.to_thread(catalog.list_rules, get_settings())
    return {"rules": rules, "privacy": "laptop-local"}


@_routes.get("/rules/{rel:path}", summary="Get rule by path")
async def rules_get(rel: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(catalog.get_rule, get_settings(), rel)
    return _require(data, f"rule not found: {rel}")


@_routes.post("/rules", summary="Create rule under ~/.asrax")
async def rules_create(body: RuleWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    if not body.rel:
        raise CatalogWriteError(code="validation", detail="rel is required", http_status=400)
    return await asyncio.to_thread(
        create_rule,
        get_settings(),
        rel=body.rel,
        body=body.body,
        description=body.description or "",
        always_apply=body.always_apply,
        globs=body.globs,
        force=body.force,
    )


@_routes.put("/rules/{rel:path}", summary="Update rule")
async def rules_update(rel: str, body: RuleWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(
        update_rule,
        get_settings(),
        rel=rel,
        body=body.body,
        description=body.description,
        always_apply=body.always_apply,
        globs=body.globs,
        expected_mtime=body.expected_mtime,
        force=body.force,
        raw=body.raw,
    )


@_routes.delete("/rules/{rel:path}", summary="Delete rule")
async def rules_delete(
    rel: str,
    confirm: int = Query(0),
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    return await asyncio.to_thread(delete_rule, get_settings(), rel=rel, confirm=bool(confirm))


@_routes.get(
    "/hooks",
    summary="List hooks",
    response_model=AsraxHooksListResponse,
)
async def hooks_list(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    hooks = await asyncio.to_thread(catalog.list_hooks, get_settings())
    return {"hooks": hooks, "privacy": "laptop-local"}


@_routes.get("/hooks/{name}", summary="Get hook by name")
async def hooks_get(name: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(catalog.get_hook, get_settings(), name)
    return _require(data, f"hook not found: {name}")


@_routes.post("/hooks", summary="Create hook under ~/.asrax")
async def hooks_create(body: HookWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    if not body.name:
        raise CatalogWriteError(code="validation", detail="name is required", http_status=400)
    return await asyncio.to_thread(
        create_hook,
        get_settings(),
        name=body.name,
        content=body.content,
        force=body.force,
    )


@_routes.put("/hooks/{name}", summary="Update hook")
async def hooks_update(name: str, body: HookWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(
        update_hook,
        get_settings(),
        name=name,
        content=body.content,
        expected_mtime=body.expected_mtime,
        force=body.force,
    )


@_routes.delete("/hooks/{name}", summary="Delete hook")
async def hooks_delete(
    name: str,
    confirm: int = Query(0),
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    return await asyncio.to_thread(delete_hook, get_settings(), name=name, confirm=bool(confirm))


@_routes.get(
    "/agents",
    summary="List agents",
    response_model=AsraxAgentsListResponse,
)
async def agents_list(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    agents = await asyncio.to_thread(catalog.list_agents, get_settings())
    return {"agents": agents, "privacy": "laptop-local"}


@_routes.get("/agents/{rel:path}", summary="Get agent by path")
async def agents_get(rel: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(catalog.get_agent, get_settings(), rel)
    return _require(data, f"agent not found: {rel}")


@_routes.post("/agents", summary="Create agent under ~/.asrax")
async def agents_create(body: AgentWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    if not body.rel:
        raise CatalogWriteError(code="validation", detail="rel is required", http_status=400)
    return await asyncio.to_thread(
        create_agent,
        get_settings(),
        rel=body.rel,
        body=body.body,
        force=body.force,
    )


@_routes.put("/agents/{rel:path}", summary="Update agent")
async def agents_update(rel: str, body: AgentWriteRequest, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(
        update_agent,
        get_settings(),
        rel=rel,
        body=body.body,
        expected_mtime=body.expected_mtime,
        force=body.force,
    )


@_routes.delete("/agents/{rel:path}", summary="Delete agent")
async def agents_delete(
    rel: str,
    confirm: int = Query(0),
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    return await asyncio.to_thread(delete_agent, get_settings(), rel=rel, confirm=bool(confirm))


@_routes.get("/agents-bootstrap", summary="Single payload for Agents UI (list + catalogs)")
async def agents_bootstrap(ctx: AuthContext = Depends(require_auth)):
    data = await asyncio.to_thread(profiles.build_agents_bootstrap, get_settings())
    data["roles"] = list(ctx.roles)
    data["subject"] = ctx.subject
    data["email"] = ctx.email
    return data


@_routes.get("/agent-workspace/{name}", summary="Agent detail + binding + effective in one call")
async def agent_workspace(name: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(profiles.build_agent_workspace, get_settings(), name)


@_routes.get("/profiles", summary="List agent profile packs", response_model=ProfilesListResponse)
async def profiles_list(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    rows = await asyncio.to_thread(profiles.list_profiles, get_settings())
    return {"profiles": rows, "privacy": "laptop-local"}


@_routes.get("/profiles/{profile_id}", summary="Get profile pack")
async def profiles_get(profile_id: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(profiles.get_profile, get_settings(), profile_id)
    return _require(data, f"profile not found: {profile_id}")


@_routes.put("/profiles/{profile_id}", summary="Update profile pack", response_model=ProfilePack)
async def profiles_put(profile_id: str, body: ProfilePack, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    return await asyncio.to_thread(
        profiles.put_profile,
        get_settings(),
        profile_id,
        body.model_dump(),
    )


@_routes.post("/agent-bindings/seed", summary="Seed missing agent bindings from catalog defaults")
async def bindings_seed(body: SeedBindingsRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    return await asyncio.to_thread(profiles.seed_bindings, get_settings(), force=body.force)


@_routes.get("/agent-bindings/{name}", summary="Get agent profile binding")
async def binding_get(name: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    data = await asyncio.to_thread(profiles.get_binding, get_settings(), name)
    if data is None:
        return {
            "agent": name,
            "profile": "",
            "skills_add": [],
            "skills_drop": [],
            "tools_add": [],
            "tools_drop": [],
            "rules_mode": "inherit",
            "notes": "",
            "privacy": "laptop-local",
        }
    return data


@_routes.put("/agent-bindings/{name}", summary="Put agent profile binding", response_model=AgentBinding)
async def binding_put(name: str, body: AgentBinding, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    return await asyncio.to_thread(profiles.put_binding, get_settings(), name, body.model_dump())


@_routes.get("/agent-bindings/{name}/effective", summary="Resolved effective brief")
async def binding_effective(name: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(profiles.resolve_effective, get_settings(), name)


@_routes.post("/agent-bindings/{name}/apply", summary="Write effective brief + soft IDE hooks")
async def binding_apply(name: str, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    return await asyncio.to_thread(profiles.apply_effective, get_settings(), name)


@_routes.get("/mcp-env-access", summary="Per-env MCP enabled/write matrix")
async def mcp_env_access_get(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    return await asyncio.to_thread(mcp_env_access.read_access, get_settings())


@_routes.put("/mcp-env-access", summary="Update per-env MCP access matrix")
async def mcp_env_access_put(body: McpEnvAccessPut, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_env(ctx, body.active_env)
    matrix_raw = {
        slug: {env: cell.model_dump() for env, cell in envs.items()}
        for slug, envs in body.matrix.items()
    }
    if not is_platform_admin(ctx):
        current = await asyncio.to_thread(mcp_env_access.read_access, get_settings())
        merged = dict(current["matrix"])
        env = body.active_env.strip().lower()
        for slug, envs in matrix_raw.items():
            row = dict(
                merged.get(slug)
                or {e: {"enabled": False, "write": False} for e in ("dev", "preprod", "prod")}
            )
            if env in envs:
                row[env] = envs[env]
            merged[slug] = row
        matrix_raw = merged
    return await asyncio.to_thread(
        mcp_env_access.write_access,
        get_settings(),
        matrix=matrix_raw,
        active_env=body.active_env,
        apply_active=body.apply_active,
    )


# --- Tasks pipeline ---


@_routes.get("/tasks", summary="List laptop tasks")
async def tasks_list(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    from am_mcp_hub.services import task_queue as tasks

    return {"tasks": await asyncio.to_thread(tasks.list_tasks, get_settings()), "privacy": "laptop-local"}


@_routes.post("/tasks", summary="Create task")
async def tasks_create(body: TaskCreateRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(
        tasks.create_task,
        get_settings(),
        title=body.title,
        body=body.body,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        connection_id=body.connection_id,
    )


@_routes.get("/tasks/{task_id}", summary="Get task")
async def tasks_get(task_id: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(tasks.get_task, get_settings(), task_id)


@_routes.patch("/tasks/{task_id}", summary="Patch task")
async def tasks_patch(task_id: str, body: TaskPatchRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(
        tasks.patch_task,
        get_settings(),
        task_id,
        title=body.title,
        body=body.body,
        assignee_type=body.assignee_type,
        assignee_id=body.assignee_id,
        connection_id=body.connection_id,
        status=body.status,
        phase=body.phase,
    )


@_routes.post("/tasks/{task_id}/analyze", summary="Heuristic (+ optional LLM) analyze")
async def tasks_analyze(task_id: str, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_pipeline as pipe
    from am_mcp_hub.services import task_queue as tasks

    settings = get_settings()
    task = await asyncio.to_thread(tasks.get_task_raw, settings, task_id)
    base = pipe.analyze_heuristic(settings, task)
    base = await pipe._maybe_llm_analyze(settings, task, base)  # noqa: SLF001
    return await asyncio.to_thread(
        tasks.set_analysis,
        settings,
        task_id,
        suggested_agent=base["suggested_agent"],
        suggested_profile=base["suggested_profile"],
        rationale=base["rationale"],
    )


@_routes.post("/tasks/{task_id}/assign-and-run", summary="Queue full pipeline")
async def tasks_assign_and_run(task_id: str, body: TaskAssignRunRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_pipeline as pipe

    return pipe.start_pipeline_job(get_settings(), task_id, connection_id=body.connection_id)


@_routes.post("/tasks/{task_id}/cancel", summary="Cancel pipeline")
async def tasks_cancel(task_id: str, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(tasks.cancel_task, get_settings(), task_id)


@_routes.post("/tasks/{task_id}/steps", summary="Append timeline step")
async def tasks_add_step(task_id: str, body: TaskStepRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(
        tasks.add_step,
        get_settings(),
        task_id,
        kind=body.kind,
        title=body.title,
        detail=body.detail,
        tool_name=body.tool_name,
        ok=body.ok,
        connection_id=body.connection_id,
        provider_kind=body.provider_kind,
    )


@_routes.post("/tasks/{task_id}/claim", summary="Claim task for a phase")
async def tasks_claim(task_id: str, phase: str = Query("develop"), ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(tasks.claim_task, get_settings(), task_id, phase=phase)


@_routes.post("/tasks/{task_id}/complete-phase", summary="Complete a pipeline phase")
async def tasks_complete_phase(task_id: str, body: TaskCompletePhaseRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(
        tasks.complete_phase,
        get_settings(),
        task_id,
        phase=body.phase,
        ok=body.ok,
        summary=body.summary,
    )


@_routes.post("/tasks/{task_id}/complete", summary="Mark task done/failed")
async def tasks_complete(task_id: str, body: TaskCompleteRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(
        tasks.complete_task,
        get_settings(),
        task_id,
        summary=body.summary,
        ok=body.ok,
    )


@_routes.post("/tasks/{task_id}/set-analysis", summary="Set analysis fields")
async def tasks_set_analysis(task_id: str, body: TaskAnalysisRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_queue as tasks

    return await asyncio.to_thread(
        tasks.set_analysis,
        get_settings(),
        task_id,
        suggested_agent=body.suggested_agent,
        suggested_profile=body.suggested_profile,
        rationale=body.rationale,
    )


@_routes.get("/tasks/{task_id}/report", summary="Get or build report")
async def tasks_report(task_id: str, ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    from am_mcp_hub.services import task_queue as tasks

    task = await asyncio.to_thread(tasks.write_report, get_settings(), task_id)
    return {"ok": True, "task": task, "report": task.get("report"), "privacy": "laptop-local"}


@_routes.post("/tasks/{task_id}/continue", summary="Continue after host IDE phase")
async def tasks_continue(task_id: str, phase: str = Query("develop"), ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_pipeline as pipe

    return await pipe.continue_from_host(get_settings(), task_id, from_phase=phase)


@_routes.get("/connections", summary="List runner connections")
async def connections_list(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    from am_mcp_hub.services import task_connections as conns

    return await asyncio.to_thread(conns.list_connections, get_settings())


@_routes.put("/connections", summary="Upsert runner connection")
async def connections_put(body: ConnectionUpsertRequest, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_connections as conns

    return await asyncio.to_thread(conns.upsert_connection, get_settings(), body.model_dump())


@_routes.delete("/connections/{connection_id}", summary="Delete connection")
async def connections_delete(connection_id: str, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_connections as conns

    return await asyncio.to_thread(conns.delete_connection, get_settings(), connection_id)


@_routes.post("/connections/{connection_id}/test", summary="Test connection")
async def connections_test(connection_id: str, ctx: AuthContext = Depends(require_auth)):
    assert_can_write_catalog(ctx)
    from am_mcp_hub.services import task_connections as conns

    return await conns.test_connection(get_settings(), connection_id)


def _unique_id(prefix: str):
    def _gen(route: APIRoute) -> str:
        return f"{prefix}_{route.name}"

    return _gen


router = APIRouter(
    prefix="/api/v1/asrax",
    tags=["asrax"],
    generate_unique_id_function=_unique_id("asrax"),
)
router.include_router(_routes)

deprecated_router = APIRouter(
    prefix="/api/v1/laptop",
    tags=["asrax"],
    deprecated=True,
    generate_unique_id_function=_unique_id("laptop"),
)
deprecated_router.include_router(_routes)
