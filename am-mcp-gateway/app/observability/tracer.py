import asyncio
import base64
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

observability_queue = asyncio.Queue(maxsize=1000)


class ObservabilityTracer:
    def __init__(self):
        self.langfuse_enabled = settings.LANGFUSE_ENABLED
        self.mlflow_enabled = settings.MLFLOW_ENABLED
        self._mlflow_initialized = False

    def _langfuse_auth_header(self) -> str | None:
        if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
            return None
        token = f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}"
        return base64.b64encode(token.encode()).decode()

    async def log_trace(
        self,
        user_id: str,
        prompt: str,
        response: str,
        model: str,
        latency: float,
        trace_id: str,
        session_id: Optional[str] = None,
        cached: bool = False,
        *,
        temperature: float | None = None,
        stream: bool | None = None,
        tools_used: list[str] | None = None,
        provider: str = "litellm",
        usage: dict[str, int] | None = None,
    ):
        """Asynchronously queues trace data to prevent blocking requests."""
        if not (self.langfuse_enabled or self.mlflow_enabled):
            return

        trace_data = {
            "user_id": user_id,
            "prompt": prompt,
            "response": response,
            "model": model,
            "latency": latency,
            "trace_id": trace_id,
            "session_id": session_id,
            "cached": cached,
            "temperature": temperature,
            "stream": stream,
            "tools_used": tools_used or [],
            "provider": provider,
            "usage": usage,
            "timestamp": time.time(),
        }

        try:
            observability_queue.put_nowait(trace_data)
        except asyncio.QueueFull:
            logger.warning("Observability queue is full. Dropping trace to prevent memory leak.")

    async def _send_to_langfuse(self, data: Dict[str, Any]):
        """Log trace via Langfuse public ingestion API (SDK-version agnostic)."""
        auth = self._langfuse_auth_header()
        if not auth:
            logger.warning("Langfuse keys missing — skipping trace")
            return

        host = settings.LANGFUSE_HOST.rstrip("/")
        url = f"{host}/api/public/ingestion"
        now = datetime.now(timezone.utc).isoformat()
        generation_id = str(uuid.uuid4())

        request_input = {
            "message": data["prompt"],
            "model": data["model"],
            "temperature": data.get("temperature"),
            "stream": data.get("stream"),
        }
        trace_metadata = {
            "provider": data.get("provider", "litellm"),
            "cached": data["cached"],
            "latency_seconds": round(data["latency"], 3),
            "tools_used": data.get("tools_used", []),
            "gateway": "am-mcp-gateway",
        }
        generation_metadata = {
            "latency_seconds": round(data["latency"], 3),
            "temperature": data.get("temperature"),
            "stream": data.get("stream"),
            "cached": data["cached"],
        }

        generation_body: dict[str, Any] = {
            "id": generation_id,
            "traceId": data["trace_id"],
            "name": "llm-call",
            "model": data["model"],
            "input": request_input,
            "output": data["response"],
            "metadata": generation_metadata,
        }
        usage = data.get("usage")
        if usage:
            generation_body["usageDetails"] = {
                "input": usage.get("prompt_tokens"),
                "output": usage.get("completion_tokens"),
                "total": usage.get("total_tokens"),
            }

        batch = [
            {
                "id": str(uuid.uuid4()),
                "type": "trace-create",
                "timestamp": now,
                "body": {
                    "id": data["trace_id"],
                    "name": "am-mcp-gateway-chat",
                    "userId": data["user_id"],
                    "sessionId": data.get("session_id"),
                    "input": request_input,
                    "output": data["response"],
                    "metadata": trace_metadata,
                },
            },
            {
                "id": str(uuid.uuid4()),
                "type": "generation-create",
                "timestamp": now,
                "body": generation_body,
            },
        ]

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Basic {auth}",
                        "Content-Type": "application/json",
                    },
                    json={"batch": batch},
                )
            if resp.status_code not in (200, 207):
                logger.error(
                    "Langfuse ingestion failed [%s]: %s",
                    resp.status_code,
                    resp.text[:500],
                )
                return
            payload = resp.json()
            errors = payload.get("errors") or []
            if errors:
                logger.error("Langfuse ingestion batch errors: %s", errors[:3])
                return
            logger.debug("Langfuse trace sent: %s", data["trace_id"])
        except Exception as e:
            logger.error(f"Langfuse trace logging failed: {e}")

    def _send_to_mlflow_sync(self, data: Dict[str, Any]) -> None:
        """Log metrics and params to MLflow as a run (blocking — run via thread pool)."""
        if not self._mlflow_initialized and self.mlflow_enabled:
            try:
                import mlflow
                mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
                mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)
                self._mlflow_initialized = True
                logger.info(
                    "MLflow tracking initialized → %s / %s",
                    settings.MLFLOW_TRACKING_URI,
                    settings.MLFLOW_EXPERIMENT_NAME,
                )
            except Exception as e:
                logger.error(f"Failed to initialize MLflow: {e}")
                return

        if not self._mlflow_initialized:
            return

        try:
            import mlflow
            with mlflow.start_run(run_name=f"chat-{data['trace_id'][:8]}"):
                mlflow.set_tags({
                    "user_id": data["user_id"],
                    "model": data["model"],
                    "session_id": data.get("session_id", ""),
                    "cached": str(data["cached"]),
                    "gateway": "am-mcp-gateway",
                    "provider": data.get("provider", "litellm"),
                })
                mlflow.log_params({
                    "model": data["model"],
                    "prompt_length": len(data["prompt"]),
                    "response_length": len(data["response"]),
                    "temperature": data.get("temperature"),
                    "stream": data.get("stream"),
                })
                metrics = {
                    "latency_seconds": round(data["latency"], 3),
                }
                usage = data.get("usage") or {}
                if usage.get("prompt_tokens") is not None:
                    metrics["prompt_tokens"] = usage["prompt_tokens"]
                if usage.get("completion_tokens") is not None:
                    metrics["completion_tokens"] = usage["completion_tokens"]
                mlflow.log_metrics(metrics)
                mlflow.log_text(data["prompt"], "prompt.txt")
                mlflow.log_text(data["response"], "response.txt")
            logger.debug(f"MLflow run logged for trace: {data['trace_id']}")
        except Exception as e:
            logger.error(f"MLflow tracking failed: {e}")

    async def _send_to_mlflow(self, data: Dict[str, Any]) -> None:
        await asyncio.to_thread(self._send_to_mlflow_sync, data)

    async def worker(self):
        """Background worker loop to process tracing tasks."""
        logger.info("Starting ObservabilityTracer background worker...")
        while True:
            try:
                data = await observability_queue.get()

                # Langfuse first — must not be blocked by sync MLflow I/O on the event loop.
                if self.langfuse_enabled:
                    try:
                        await asyncio.wait_for(self._send_to_langfuse(data), timeout=15.0)
                    except asyncio.TimeoutError:
                        logger.warning("Langfuse logging timed out.")
                    except Exception as e:
                        logger.error(f"Langfuse logging failed: {e}")

                if self.mlflow_enabled:
                    try:
                        await asyncio.wait_for(self._send_to_mlflow(data), timeout=15.0)
                    except asyncio.TimeoutError:
                        logger.warning("MLflow logging timed out.")
                    except Exception as e:
                        logger.error(f"MLflow logging failed: {e}")

                observability_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in observability worker: {e}")
                await asyncio.sleep(1.0)


observability_tracer = ObservabilityTracer()
