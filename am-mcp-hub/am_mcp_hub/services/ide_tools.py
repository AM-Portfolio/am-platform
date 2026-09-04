"""IDE tool execute wrapping hub MCP tool handlers."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.api.mcp_router import _audit, _tools_for
from am_mcp_hub.services.auth import AuthContext
from am_mcp_hub.services.ide_bootstrap import tool_mutates


async def execute_ide_tool(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    name: str,
    arguments: dict[str, Any],
    approved: bool,
    trace_id: str | None = None,
) -> dict[str, Any]:
    mutates = tool_mutates(name)
    if mutates and not approved:
        raise HTTPException(
            status_code=403,
            detail="mutating tool requires approved=true",
        )

    tools = await _tools_for(session, ctx)
    match = next((t for t in tools if t["name"] == name), None)
    if match is None:
        await _audit(session, ctx, tool_name=name, ok=False, detail="unknown tool")
        raise HTTPException(status_code=403, detail=f"tool not allowed: {name}")

    try:
        result = await match["handler"](arguments if isinstance(arguments, dict) else {})
        ok = bool(result.get("ok", True)) if isinstance(result, dict) else True
        await _audit(
            session,
            ctx,
            tool_name=name,
            ok=ok,
            detail=json.dumps(result, default=str)[:1500],
        )
        content = json.dumps(result, default=str, indent=2) if not isinstance(result, str) else result
        return {"ok": ok, "content": content, "traceId": trace_id or ""}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        await _audit(session, ctx, tool_name=name, ok=False, detail=str(exc))
        return {"ok": False, "content": str(exc), "traceId": trace_id or ""}
