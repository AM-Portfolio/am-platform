import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.observability.tracer import observability_tracer

# Configure logging
logging.basicConfig(
    level=logging.getLevelName(settings.LOG_LEVEL),
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s' if settings.LOG_FORMAT == 'text' else '{"time":"%(asctime)s", "level":"%(levelname)s", "name":"%(name)s", "message":"%(message)s"}',
)
logger = logging.getLogger("am-mcp-gateway")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch background worker for observability
    worker_task = asyncio.create_task(observability_tracer.worker())
    logger.info("Observability background tracing worker started.")
    yield
    # Shutdown: Cancel worker and allow cleanup
    logger.info("Shutting down observability background tracing worker...")
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Gateway service stopped.")

app = FastAPI(
    title="AM MCP Gateway",
    description="Intelligent AI Routing layer with SSO, Caching, and Tracing",
    version="2.0.0",
    lifespan=lifespan
)

# Wire CORS middleware based on settings config
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Routers
app.include_router(chat_router, prefix="/api/v1")
app.include_router(health_router)
