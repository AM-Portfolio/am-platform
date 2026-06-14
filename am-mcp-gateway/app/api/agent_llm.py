"""Service-to-service LLM endpoint for internal agents (e.g. ui-test-agent).

Routes through LiteLLM so all agent LLM/vision calls appear in LiteLLM logs + Langfuse.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from am_platform_security.dependencies import require_auth_context
from am_platform_security.models import AuthContext

from app.api.chat import _litellm_metadata, _log_chat_trace
from app.llm.router import llm_router

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)


class AgentLLMRequest(BaseModel):
    messages: list[dict[str, Any]] = Field(..., description="OpenAI-style messages (text or multimodal)")
    model: str = Field(..., description="LiteLLM model name")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1, le=8192)
    sessionId: Optional[str] = None
    testId: Optional[str] = Field(default=None, description="UI test run id for trace correlation")
    source: str = Field(default="ui-test-agent", description="Caller service name")


class AgentLLMResponse(BaseModel):
    content: str
    model: str
    sessionId: str
    traceId: str
    usage: dict[str, int] | None = None


def _prompt_summary(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            parts.append(content[:500])
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", ""))[:500])
    return "\n".join(parts)[:2000] or "(multimodal request)"


@router.post("/agent/llm/completions", response_model=AgentLLMResponse)
async def agent_llm_completions(
    request: AgentLLMRequest,
    auth_context: AuthContext = Depends(require_auth_context()),
):
    """Proxy agent LLM/vision calls to LiteLLM with gateway + Langfuse tracing."""
    user_id = auth_context.subject
    session_id = request.sessionId or request.testId or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    start_time = time.time()

    metadata = _litellm_metadata(user_id=user_id, session_id=session_id, trace_id=trace_id)
    metadata["source"] = request.source
    if request.testId:
        metadata["test_id"] = request.testId

    response_text, provider, usage = await llm_router.generate_chat_messages(
        request.messages,
        model=request.model,
        temperature=request.temperature,
        metadata=metadata,
        max_tokens=request.max_tokens,
    )
    latency = time.time() - start_time

    await _log_chat_trace(
        user_id=user_id,
        session_id=session_id,
        trace_id=trace_id,
        response=response_text,
        model=request.model,
        latency=latency,
        provider=provider,
        usage=usage,
        request=_AgentTraceRequest(
            message=_prompt_summary(request.messages),
            model=request.model,
            temperature=request.temperature,
            stream=False,
        ),
    )

    logger.info(
        "Agent LLM completion source=%s test_id=%s model=%s latency=%.2fs",
        request.source,
        request.testId,
        request.model,
        latency,
    )
    return AgentLLMResponse(
        content=response_text,
        model=request.model,
        sessionId=session_id,
        traceId=trace_id,
        usage=usage,
    )


class _AgentTraceRequest:
    """Minimal adapter so agent calls reuse chat trace logging."""

    def __init__(self, *, message: str, model: str, temperature: float, stream: bool):
        self.message = message
        self.model = model
        self.temperature = temperature
        self.stream = stream
