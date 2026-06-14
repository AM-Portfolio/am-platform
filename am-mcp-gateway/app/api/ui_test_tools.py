"""MCP-oriented HTTP tools — thin proxy to am-ui-test-agent using wrapper manifests."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.tools.ui_test_resolver import load_manifest, resolve_module_target

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools/ui-test", tags=["ui-test-tools"])


class UiTestAuthRunRequest(BaseModel):
    module: str = Field(default="modern-ui", description="Wrapper module key from manifest.json")
    environment: str = Field(default="preprod", description="Target environment (local, preprod, ...)")
    target: str = Field(default="main", description="Named target inside targets.{env}.json")
    wait: bool = Field(default=True, description="Poll until test completes")
    timeout_seconds: int = Field(default=180, ge=10, le=600)


class UiTestAuthRunResponse(BaseModel):
    testId: str
    status: str
    module: str
    environment: str
    target: str
    targetUrl: str
    uiMode: str
    profile: Optional[str] = None
    report: Optional[str] = None
    reportUrl: Optional[str] = None
    error: Optional[str] = None


@router.get(
    "/manifest",
    operation_id="get_ui_test_manifest",
    summary="UI test wrapper manifest for MCP tool registration",
)
async def get_ui_test_manifest():
    """Return wrapper manifest for MCP tool registration (e.g. am-mcp-server @Tool metadata)."""
    path = Path(settings.UI_TEST_MANIFEST_PATH)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Manifest not found: {path}")
    return load_manifest(path)


@router.post(
    "/run-auth",
    response_model=UiTestAuthRunResponse,
    operation_id="run_modern_ui_auth_test",
    summary="Run am-modern-ui Demo Login auth E2E via ui-test-agent",
)
async def run_ui_test_auth(request: UiTestAuthRunRequest):
    """
    MCP tool entrypoint: resolve wrapper targets → queue auth test on ui-test-agent → optional poll.

    Designed for loose coupling: logic stays in ui-test-agent; URLs stay in am-modern-ui/testing/.
    """
    manifest_path = Path(settings.UI_TEST_MANIFEST_PATH)
    if not manifest_path.is_file():
        raise HTTPException(status_code=503, detail=f"UI test manifest missing: {manifest_path}")

    try:
        resolved = resolve_module_target(
            manifest_path,
            module=request.module,
            environment=request.environment,
            target_name=request.target,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    agent_base = settings.UI_TEST_AGENT_BASE_URL.rstrip("/")
    payload = {
        "targetUrl": resolved["target_url"],
        "uiMode": resolved["ui_mode"],
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(f"{agent_base}/api/v1/test/run/auth", json=payload)
            resp.raise_for_status()
        except httpx.ConnectError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"ui-test-agent unavailable at {agent_base}. Start: cd am-ui-test-agent && npm run preprod",
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text) from exc

        body = resp.json()
        test_id = body["testId"]

        if not request.wait:
            return UiTestAuthRunResponse(
                testId=test_id,
                status="QUEUED",
                module=resolved["module"],
                environment=resolved["environment"],
                target=resolved["target"],
                targetUrl=resolved["target_url"],
                uiMode=resolved["ui_mode"],
                profile=resolved.get("profile"),
                reportUrl=f"{agent_base}/api/v1/test/report/{test_id}",
            )

        deadline = time.monotonic() + request.timeout_seconds
        last: dict[str, Any] = {"status": "QUEUED"}
        while time.monotonic() < deadline:
            status_resp = await client.get(f"{agent_base}/api/v1/test/status/{test_id}")
            status_resp.raise_for_status()
            last = status_resp.json()
            st = last.get("status", "UNKNOWN")
            if st == "COMPLETED":
                report = last.get("report")
                return UiTestAuthRunResponse(
                    testId=test_id,
                    status=st,
                    module=resolved["module"],
                    environment=resolved["environment"],
                    target=resolved["target"],
                    targetUrl=resolved["target_url"],
                    uiMode=resolved["ui_mode"],
                    profile=resolved.get("profile"),
                    report=report,
                    reportUrl=f"{agent_base}/api/v1/test/report/{test_id}",
                )
            if st == "FAILED":
                return UiTestAuthRunResponse(
                    testId=test_id,
                    status=st,
                    module=resolved["module"],
                    environment=resolved["environment"],
                    target=resolved["target"],
                    targetUrl=resolved["target_url"],
                    uiMode=resolved["ui_mode"],
                    profile=resolved.get("profile"),
                    report=last.get("report"),
                    reportUrl=f"{agent_base}/api/v1/test/report/{test_id}",
                    error=last.get("error"),
                )
            await asyncio.sleep(3)

    raise HTTPException(status_code=504, detail=f"Timeout waiting for test {test_id}")
