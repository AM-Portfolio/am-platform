from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Shared security library imports
from am_platform_security.dependencies import require_auth_context
from am_platform_security.models import AuthContext

from app.config import settings
from app.llm.router import llm_router
from app.session.cache import response_cache
from app.tools.fin_agent_client import fin_agent_client
from app.observability.tracer import observability_tracer

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)


def _litellm_metadata(*, user_id: str, session_id: str, trace_id: str) -> dict:
    return {
        "trace_user_id": user_id,
        "session_id": session_id,
        "gateway_trace_id": trace_id,
    }


async def _log_chat_trace(
    *,
    request: ChatRequest,
    user_id: str,
    session_id: str,
    trace_id: str,
    response: str,
    model: str,
    latency: float,
    cached: bool = False,
    tools_used: list[str] | None = None,
    provider: str = "litellm",
    usage: dict[str, int] | None = None,
) -> None:
    await observability_tracer.log_trace(
        user_id=user_id,
        prompt=request.message,
        response=response,
        model=model,
        latency=latency,
        trace_id=trace_id,
        session_id=session_id,
        cached=cached,
        temperature=request.temperature,
        stream=request.stream,
        tools_used=tools_used,
        provider=provider,
        usage=usage,
    )


class ChatRequest(BaseModel):
    message: str = Field(..., description="Message input from user")
    model: str = Field(default="together_ai/meta-llama/Meta-Llama-3-8B-Instruct-Lite")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    stream: bool = Field(default=True)
    sessionId: Optional[str] = None

class ChatResponse(BaseModel):
    message: str
    widgetId: str = "TEXT_RESPONSE"
    widgetParams: Dict[str, Any] = Field(default_factory=dict)
    sessionId: str
    toolsUsed: list[str] = Field(default_factory=list)
    traceId: str
    cached: bool = False

@router.post("/chat")
async def chat_stream(
    request: ChatRequest,
    auth_context: AuthContext = Depends(require_auth_context())
):
    """
    Main SSE streaming chat endpoint.
    Routes to am-fin-agent if financial keywords are detected, otherwise calls direct LLM.
    """
    user_id = auth_context.subject
    session_id = request.sessionId or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    start_time = time.time()

    # 1. Check cache first
    cached_val = await response_cache.get(user_id, request.message, request.model)
    if cached_val:
        logger.info(f"Cache hit for user: {user_id}")
        async def cached_stream():
            yield f"data: {cached_val}\n\n"
            yield "data: [DONE]\n\n"
        
        # Async tracer logging for cached hit
        await _log_chat_trace(
            request=request,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            response=json.loads(cached_val).get("message", cached_val) if cached_val.startswith("{") else cached_val,
            model=request.model,
            latency=0.0,
            cached=True,
        )
        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # 2. Check intent routing
    is_financial = await fin_agent_client.check_financial_intent(request.message)

    if is_financial and settings.MCP_SERVER_ENABLED:
        async def financial_stream_gen():
            try:
                res = await fin_agent_client.query_agent(request.message, user_id, session_id)
                res_payload = {
                    "message": res.get("message", ""),
                    "widgetId": res.get("widgetId", "TEXT_RESPONSE"),
                    "widgetParams": res.get("widgetParams", {}),
                    "sessionId": res.get("sessionId", session_id),
                    "toolsUsed": res.get("toolsUsed", []),
                    "traceId": res.get("traceId", trace_id),
                    "cached": False
                }
                serialized = json.dumps(res_payload)
                # Cache full response
                await response_cache.set(user_id, request.message, request.model, serialized)
                
                # Yield SSE chunk
                yield f"data: {serialized}\n\n"
                yield "data: [DONE]\n\n"

                latency = time.time() - start_time
                await _log_chat_trace(
                    request=request,
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=trace_id,
                    response=res.get("message", ""),
                    model="am-fin-agent",
                    latency=latency,
                    tools_used=res.get("toolsUsed", []),
                    provider="am-fin-agent",
                )
            except Exception as e:
                logger.error(f"Failed to query financial agent: {e}. Falling back to general LLM.")
                # Fallback to general LLM on failure
                async for chunk in general_llm_stream():
                    yield chunk

        return StreamingResponse(financial_stream_gen(), media_type="text/event-stream")

    # 3. Direct general LLM streaming
    async def general_llm_stream():
        full_text = []
        actual_model = request.model
        try:
            async for chunk, _provider in llm_router.generate_chat_stream(
                request.message,
                model=request.model,
                temperature=request.temperature,
                metadata=_litellm_metadata(
                    user_id=user_id,
                    session_id=session_id,
                    trace_id=trace_id,
                ),
            ):
                full_text.append(chunk)
                yield f"data: {json.dumps({'chunk': chunk, 'model': request.model})}\n\n"
            
            combined_text = "".join(full_text)
            res_payload = {
                "message": combined_text,
                "widgetId": "TEXT_RESPONSE",
                "widgetParams": {},
                "sessionId": session_id,
                "toolsUsed": [],
                "traceId": trace_id,
                "cached": False
            }
            # Cache full response
            await response_cache.set(user_id, request.message, request.model, json.dumps(res_payload))
            
            yield "data: [DONE]\n\n"

            latency = time.time() - start_time
            await _log_chat_trace(
                request=request,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                response=combined_text,
                model=actual_model,
                latency=latency,
                usage=llm_router.last_usage,
            )
        except Exception as exc:
            logger.error(f"General LLM streaming failed: {exc}")
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(general_llm_stream(), media_type="text/event-stream")


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(
    request: ChatRequest,
    auth_context: AuthContext = Depends(require_auth_context())
):
    """
    Synchronous chat endpoint (returns full JSON immediately).
    """
    user_id = auth_context.subject
    session_id = request.sessionId or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    start_time = time.time()

    # 1. Cache lookup
    cached_val = await response_cache.get(user_id, request.message, request.model)
    if cached_val:
        logger.info(f"Cache hit (sync) for user: {user_id}")
        data = json.loads(cached_val)
        data["cached"] = True
        
        await _log_chat_trace(
            request=request,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            response=data.get("message", ""),
            model=request.model,
            latency=0.0,
            cached=True,
        )
        return ChatResponse(**data)

    # 2. Check intent routing
    is_financial = await fin_agent_client.check_financial_intent(request.message)

    if is_financial and settings.MCP_SERVER_ENABLED:
        try:
            res = await fin_agent_client.query_agent(request.message, user_id, session_id)
            latency = time.time() - start_time
            
            res_obj = ChatResponse(
                message=res.get("message", ""),
                widgetId=res.get("widgetId", "TEXT_RESPONSE"),
                widgetParams=res.get("widgetParams", {}),
                sessionId=res.get("sessionId", session_id),
                toolsUsed=res.get("toolsUsed", []),
                traceId=res.get("traceId", trace_id),
                cached=False
            )
            
            # Write to cache
            await response_cache.set(user_id, request.message, request.model, json.dumps(res_obj.model_dump()))
            
            await _log_chat_trace(
                request=request,
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
                response=res_obj.message,
                model="am-fin-agent",
                latency=latency,
                tools_used=res_obj.toolsUsed,
                provider="am-fin-agent",
            )
            return res_obj
        except Exception as e:
            logger.error(f"Synchronous financial agent call failed: {e}. Falling back to general LLM.")

    # 3. Direct general LLM call
    try:
        response_text, _provider, usage = await llm_router.generate_chat(
            request.message,
            model=request.model,
            temperature=request.temperature,
            metadata=_litellm_metadata(
                user_id=user_id,
                session_id=session_id,
                trace_id=trace_id,
            ),
        )
        latency = time.time() - start_time
        
        res_obj = ChatResponse(
            message=response_text,
            widgetId="TEXT_RESPONSE",
            widgetParams={},
            sessionId=session_id,
            toolsUsed=[],
            traceId=trace_id,
            cached=False
        )
        
        # Write to cache
        await response_cache.set(user_id, request.message, request.model, json.dumps(res_obj.model_dump()))
        
        await _log_chat_trace(
            request=request,
            user_id=user_id,
            session_id=session_id,
            trace_id=trace_id,
            response=response_text,
            model=request.model,
            latency=latency,
            usage=usage,
        )
        return res_obj
    except Exception as exc:
        logger.error(f"Synchronous general LLM failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"General LLM call failed: {str(exc)}"
        )
