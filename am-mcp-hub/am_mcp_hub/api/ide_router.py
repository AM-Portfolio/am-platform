"""AM Code IDE APIs: bootstrap, streaming chat, tool execute."""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.core.config import get_settings
from am_mcp_hub.core.database import get_db_session
from am_mcp_hub.services.auth import AuthContext, require_auth
from am_mcp_hub.services.ide_bootstrap import build_ide_bootstrap
from am_mcp_hub.services.ide_chat import stream_ide_chat
from am_mcp_hub.services.ide_prompt import build_ide_system_prompt
from am_mcp_hub.services.ide_tools import execute_ide_tool

router = APIRouter(prefix="/api/v1/ide", tags=["ide"])

# Re-export for unit tests
__all__ = ["router", "_tools_for_mode", "_normalize_tool_calls", "_messages_with_system"]

ChatMode = Literal["ask", "agent", "plan", "debug", "multitask"]

_MODE_HINTS: dict[str, str] = {
    "ask": "Mode: Ask. Answer questions only. Do not call tools.",
    "agent": "Mode: Agent. Use tools when helpful to complete the task.",
    "plan": (
        "Mode: Plan. You may call read-only tools to gather context. "
        "Produce a structured markdown plan (Summary, Plan, Architecture with mermaid, Tools, "
        "Agent assignments, Todos, Risks). Do not mutate files or run shell."
    ),
    "debug": "Mode: Debug. Focus on diagnosing errors from selection/problems context. Prefer precise root-cause analysis.",
    "multitask": "Mode: Multitask. Treat this as one of several parallel chat sessions; stay scoped to this thread.",
}

_PLAN_READONLY_EXACT = {
    "hub_status",
    "list_skills",
    "catalog_overview",
    "list_agents",
    "get_skill",
    "get_agent",
    "github_whoami",
    "list_rules",
    "ide_read_file",
    "ide_list_dir",
    "ide_glob",
    "ide_grep",
    "ide_open_file",
}


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list[Any] | None = None


class IdeContext(BaseModel):
    activeFile: str | None = None
    activeFilePath: str | None = None
    selection: str | None = None
    problems: str | None = None
    attachments: str | None = None
    mentions: str | None = None


class IdeChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    agentId: str | None = None
    mode: ChatMode | None = None
    context: IdeContext | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class IdeToolExecuteRequest(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    traceId: str | None = None


def _messages_with_system(
    messages: list[ChatMessage],
    *,
    agent_id: str | None,
    mode: str | None,
    context: IdeContext | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    has_system = any(m.role == "system" for m in messages)
    if not has_system:
        base = build_ide_system_prompt(get_settings(), agent_id=agent_id)
        hint = _MODE_HINTS.get((mode or "agent").lower(), _MODE_HINTS["agent"])
        parts = [base, hint]
        if context:
            if context.activeFilePath:
                parts.append(f"## Active file path\n{context.activeFilePath}")
            if context.activeFile:
                parts.append(f"## Active file\n```\n{context.activeFile[:32000]}\n```")
            if context.selection:
                parts.append(f"## Selection\n```\n{context.selection[:16000]}\n```")
            if context.problems:
                parts.append(f"## Problems\n{context.problems[:8000]}")
            if context.attachments:
                parts.append(f"## Attachments\n{context.attachments[:48000]}")
            if context.mentions:
                parts.append(f"## @ references\n{context.mentions[:48000]}")
        out.append({"role": "system", "content": "\n\n".join(parts)})
    for m in messages:
        item: dict[str, Any] = {"role": m.role, "content": m.content if m.content is not None else ""}
        if m.tool_call_id:
            item["tool_call_id"] = m.tool_call_id
        if m.tool_calls:
            item["tool_calls"] = _normalize_tool_calls(m.tool_calls)
        out.append(item)
    return out


def _normalize_tool_calls(raw: list[Any]) -> list[dict[str, Any]]:
    """Together/OpenAI require tool_calls[].type == 'function'."""
    out: list[dict[str, Any]] = []
    for i, tc in enumerate(raw):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = fn.get("name") or tc.get("name")
        if not name:
            continue
        args = fn.get("arguments", "{}")
        if not isinstance(args, str):
            args = json.dumps(args)
        out.append(
            {
                "id": str(tc.get("id") or f"call_{i}"),
                "type": "function",
                "function": {"name": str(name), "arguments": args or "{}"},
            }
        )
    return out


def _tools_for_mode(mode: str | None, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    m = (mode or "agent").lower()
    if m == "ask":
        return None
    if m == "plan":
        if not tools:
            return None
        out: list[dict[str, Any]] = []
        for t in tools:
            name = str((t.get("function") or {}).get("name") or t.get("name") or "")
            if name in _PLAN_READONLY_EXACT:
                out.append(t)
        return out or None
    return tools


@router.get("/bootstrap", summary="IDE entitlement pack")
async def ide_bootstrap(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    base = str(request.base_url).rstrip("/")
    return await build_ide_bootstrap(session, ctx, request_base=base)


@router.post("/chat", summary="Streaming IDE chat (SSE)")
async def ide_chat(
    body: IdeChatRequest,
    ctx: AuthContext = Depends(require_auth),
) -> StreamingResponse:
    settings = get_settings()
    messages = _messages_with_system(
        body.messages,
        agent_id=body.agentId,
        mode=body.mode,
        context=body.context,
    )
    tools = _tools_for_mode(body.mode, body.tools)
    gen = stream_ide_chat(
        ctx,
        messages=messages,
        model=body.model,
        tools=tools,
        tool_choice=body.tool_choice if tools else None,
        settings=settings,
        rpm=30,
        daily_tokens=500_000,
    )
    return StreamingResponse(
        gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/tools/execute", summary="Execute entitled MCP tool")
async def ide_tools_execute(
    body: IdeToolExecuteRequest,
    ctx: AuthContext = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    return await execute_ide_tool(
        session,
        ctx,
        name=body.name,
        arguments=body.arguments,
        approved=body.approved,
        trace_id=body.traceId,
    )
