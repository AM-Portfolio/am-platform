import os
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from am_identity.api.admin_router import router as admin_router
from am_identity.api.auth_router import router as auth_router
from am_identity.api.internal_router import router as internal_router
from am_identity.api.user_router import router as user_router
from am_identity.core.config import get_settings
from am_platform_common import LoggingMiddleware, setup_logging

settings = get_settings()
setup_logging(env=settings.app_env)

async def run_purge_every_5_minutes():
    # Dynamically locate project root and add to sys.path
    root_dir = Path(__file__).resolve().parent.parent.parent
    sys.path.append(str(root_dir))
    
    try:
        from automation.scripts.purge_deleted_accounts import main as run_purge
    except ImportError as e:
        print(f"⚠️ [BACKGROUND SCHEDULER] Could not import purge script: {e}")
        return

    # Set DEV/LOCAL test period to 5 minutes
    if "PURGE_PERIOD_MINUTES" not in os.environ:
        os.environ["PURGE_PERIOD_MINUTES"] = "5"
    
    while True:
        try:
            print("🕒 [BACKGROUND SCHEDULER] Running account purge task...")
            await run_purge()
        except Exception as e:
            print(f"❌ [BACKGROUND SCHEDULER] Error in purge execution: {e}")
            
        await asyncio.sleep(300) # Sleep for 5 minutes

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.app_env.lower() in ("dev", "local"):
        print("🚀 [BACKGROUND SCHEDULER] Starting dev/local background purge scheduler (5 minutes interval)...")
        asyncio.create_task(run_purge_every_5_minutes())
    yield

app = FastAPI(
    title="AM Identity Service",
    version="0.1.0",
    description="Unified Keycloak-backed identity layer for AM Platform",
    lifespan=lifespan,
)
app.add_middleware(LoggingMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(admin_router)
app.include_router(internal_router)

