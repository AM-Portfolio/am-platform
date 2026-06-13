import asyncio
import logging
import time
from typing import Any, Dict, Optional
from app.config import settings

logger = logging.getLogger(__name__)

# Bounded queue to limit memory consumption if Langfuse/MLflow are down
observability_queue = asyncio.Queue(maxsize=1000)


class ObservabilityTracer:
    def __init__(self):
        self.langfuse_enabled = settings.LANGFUSE_ENABLED
        self.mlflow_enabled = settings.MLFLOW_ENABLED
        self._langfuse_client = None
        self._mlflow_initialized = False

    def _get_langfuse(self):
        """Lazy-init Langfuse client — avoids import errors if not enabled."""
        if self._langfuse_client is None and self.langfuse_enabled:
            try:
                from langfuse import Langfuse
                self._langfuse_client = Langfuse(
                    public_key=settings.LANGFUSE_PUBLIC_KEY,
                    secret_key=settings.LANGFUSE_SECRET_KEY,
                    host=settings.LANGFUSE_HOST,
                    flush_interval=settings.LANGFUSE_FLUSH_INTERVAL_SECONDS,
                )
                logger.info(f"Langfuse client initialized → {settings.LANGFUSE_HOST}")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse client: {e}")
        return self._langfuse_client

    def _init_mlflow(self):
        """Lazy-init MLflow tracking URI."""
        if not self._mlflow_initialized and self.mlflow_enabled:
            try:
                import mlflow
                mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
                mlflow.set_experiment(settings.MLFLOW_EXPERIMENT_NAME)
                self._mlflow_initialized = True
                logger.info(f"MLflow tracking initialized → {settings.MLFLOW_TRACKING_URI} / {settings.MLFLOW_EXPERIMENT_NAME}")
            except Exception as e:
                logger.error(f"Failed to initialize MLflow: {e}")

    async def log_trace(
        self,
        user_id: str,
        prompt: str,
        response: str,
        model: str,
        latency: float,
        trace_id: str,
        session_id: Optional[str] = None,
        cached: bool = False
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
            "timestamp": time.time()
        }

        try:
            observability_queue.put_nowait(trace_data)
        except asyncio.QueueFull:
            logger.warning("Observability queue is full. Dropping trace to prevent memory leak.")

    async def _send_to_langfuse(self, data: Dict[str, Any]):
        """Log trace to Langfuse using the Python SDK."""
        client = self._get_langfuse()
        if not client:
            return
        try:
            trace = client.trace(
                id=data["trace_id"],
                name="am-mcp-gateway-chat",
                user_id=data["user_id"],
                session_id=data.get("session_id"),
                metadata={
                    "model": data["model"],
                    "cached": data["cached"],
                    "latency_seconds": round(data["latency"], 3),
                }
            )
            # Log the generation span
            trace.generation(
                name="llm-call",
                model=data["model"],
                input=data["prompt"],
                output=data["response"],
                usage={
                    "input": len(data["prompt"].split()),
                    "output": len(data["response"].split()),
                },
                metadata={"latency_seconds": round(data["latency"], 3)},
            )
            client.flush()
            logger.debug(f"Langfuse trace sent: {data['trace_id']}")
        except Exception as e:
            logger.error(f"Langfuse trace logging failed: {e}")

    async def _send_to_mlflow(self, data: Dict[str, Any]):
        """Log metrics and params to MLflow as a run."""
        self._init_mlflow()
        if not self._mlflow_initialized:
            return
        try:
            import mlflow
            # Use run_name = trace_id so each conversation turn is identifiable
            with mlflow.start_run(run_name=f"chat-{data['trace_id'][:8]}"):
                mlflow.set_tags({
                    "user_id": data["user_id"],
                    "model": data["model"],
                    "session_id": data.get("session_id", ""),
                    "cached": str(data["cached"]),
                    "gateway": "am-mcp-gateway",
                })
                mlflow.log_params({
                    "model": data["model"],
                    "prompt_length": len(data["prompt"]),
                    "response_length": len(data["response"]),
                })
                mlflow.log_metrics({
                    "latency_seconds": round(data["latency"], 3),
                    "prompt_tokens_est": len(data["prompt"].split()),
                    "response_tokens_est": len(data["response"].split()),
                })
                # Log full prompt + response as artifact text
                mlflow.log_text(data["prompt"], "prompt.txt")
                mlflow.log_text(data["response"], "response.txt")
            logger.debug(f"MLflow run logged for trace: {data['trace_id']}")
        except Exception as e:
            logger.error(f"MLflow tracking failed: {e}")

    async def worker(self):
        """Background worker loop to process tracing tasks."""
        logger.info("Starting ObservabilityTracer background worker...")
        while True:
            try:
                data = await observability_queue.get()

                # Run tracing payloads concurrently with a strict 5-second timeout
                tasks = []
                if self.langfuse_enabled:
                    tasks.append(self._send_to_langfuse(data))
                if self.mlflow_enabled:
                    tasks.append(self._send_to_mlflow(data))

                if tasks:
                    try:
                        await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)
                    except asyncio.TimeoutError:
                        logger.warning("Observability logging timed out. Skipping chunk.")
                    except Exception as e:
                        logger.error(f"Error executing observability task: {e}")

                observability_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in observability worker: {e}")
                await asyncio.sleep(1.0)


observability_tracer = ObservabilityTracer()
