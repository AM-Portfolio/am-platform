from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from am_mcp_hub.api.admin_router import router as admin_router
from am_mcp_hub.api.asrax_router import catalog_write_exception_handler
from am_mcp_hub.api.asrax_router import deprecated_router as asrax_deprecated_router
from am_mcp_hub.api.asrax_router import router as asrax_router
from am_mcp_hub.api.creds_router import router as creds_router
from am_mcp_hub.api.google_proxy import router as google_proxy_router
from am_mcp_hub.api.ide_router import router as ide_router
from am_mcp_hub.api.mcp_router import router as mcp_router
from am_mcp_hub.core.config import get_settings
from am_mcp_hub.core.database import init_db
from am_mcp_hub.services import local_creds as local_creds
from am_mcp_hub.services.catalog_write import CatalogWriteError

settings = get_settings()
ADMIN_DIR = Path(__file__).resolve().parents[1] / "admin-ui"


@asynccontextmanager
async def lifespan(_: FastAPI):
    local_creds.ensure_samples_copied()
    local_creds.load_into_environ()
    await init_db()
    yield


app = FastAPI(
    title="AM MCP Hub",
    version="0.1.0",
    description="Postgres-backed MCP catalog + aggregated HTTPS MCP for Asrax",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "integrations", "description": "Org integration registry"},
        {"name": "marketplace", "description": "Hub + asrax MCP marketplace"},
        {"name": "ui", "description": "Admin UI bootstrap"},
        {"name": "google", "description": "Google Workspace status"},
        {"name": "asrax", "description": "Mounted ~/.asrax catalog and chat memory"},
        {"name": "local-creds", "description": "Host-local credentials"},
        {"name": "mcp", "description": "MCP transports and hub tools"},
        {"name": "google-proxy", "description": "Google Workspace MCP proxy"},
        {"name": "ide", "description": "VS Code / AM Code IDE bootstrap and chat"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5179",
        "http://localhost:5179",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8787",
        "http://localhost:8787",
        "null",
    ],
    allow_origin_regex=r"^vscode-webview://.*$|^https?://127\.0\.0\.1:\d+$|^https?://localhost:\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(CatalogWriteError, catalog_write_exception_handler)
app.include_router(admin_router)
app.include_router(asrax_router)
app.include_router(asrax_deprecated_router)
app.include_router(ide_router)
app.include_router(mcp_router)
app.include_router(google_proxy_router)
app.include_router(creds_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "am-mcp-hub"}


@app.get("/")
async def root():
    home = ADMIN_DIR / "home.html"
    if home.is_file():
        return FileResponse(home)
    if ADMIN_DIR.is_dir():
        return RedirectResponse(url="/admin/")
    return {
        "service": "am-mcp-hub",
        "health": "/health",
        "mcp": "/mcp",
        "admin": "/admin/",
        "docs": "/docs",
    }


@app.get("/.well-known/oauth-protected-resource")
@app.get("/.well-known/oauth-protected-resource/{path:path}")
async def oauth_protected_resource(request: Request, path: str = ""):
    """MCP clients probe this; hub auth is Bearer/API-key, not interactive OAuth."""
    base = str(request.base_url).rstrip("/")
    return {
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": [],
    }


@app.get("/.well-known/oauth-authorization-server")
@app.get("/.well-known/oauth-authorization-server/{path:path}")
async def oauth_authorization_server(request: Request, path: str = ""):
    base = str(request.base_url).rstrip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["client_credentials", "authorization_code"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "none"],
        "code_challenge_methods_supported": ["S256"],
    }


@app.api_route("/oauth/{rest:path}", methods=["GET", "POST"])
async def oauth_stub(rest: str):
    return JSONResponse(
        {
            "error": "oauth_not_required",
            "message": "Use Asrax API key / Bearer on /mcp (or HUB_DEV_BYPASS_AUTH locally)",
            "path": rest,
        },
        status_code=501,
    )


if ADMIN_DIR.is_dir():
    app.mount("/admin/assets", StaticFiles(directory=ADMIN_DIR), name="admin-assets")

    @app.get("/admin")
    @app.get("/admin/")
    async def admin_index():
        return FileResponse(ADMIN_DIR / "index.html")

    @app.get("/tools")
    @app.get("/tools/")
    async def tools_ui():
        return FileResponse(ADMIN_DIR / "tools.html")

    @app.get("/marketplace")
    @app.get("/marketplace/")
    async def marketplace_ui():
        return FileResponse(ADMIN_DIR / "marketplace.html")

    @app.get("/catalog")
    @app.get("/catalog/")
    async def catalog_ui():
        return FileResponse(ADMIN_DIR / "catalog.html")

    @app.get("/google")
    @app.get("/google/")
    async def google_ui():
        return FileResponse(ADMIN_DIR / "google.html")

    @app.get("/history")
    @app.get("/history/")
    async def history_ui():
        return FileResponse(ADMIN_DIR / "history.html")

    @app.get("/skills")
    @app.get("/skills/")
    async def skills_ui():
        return FileResponse(ADMIN_DIR / "library.html")

    @app.get("/rules")
    @app.get("/rules/")
    async def rules_ui():
        return FileResponse(ADMIN_DIR / "library.html")

    @app.get("/hooks")
    @app.get("/hooks/")
    async def hooks_ui():
        return FileResponse(ADMIN_DIR / "library.html")

    @app.get("/agents")
    @app.get("/agents/")
    async def agents_ui():
        return FileResponse(ADMIN_DIR / "agents.html")

    @app.get("/tasks")
    @app.get("/tasks/")
    async def tasks_ui():
        return FileResponse(ADMIN_DIR / "tasks.html")

    @app.get("/work")
    @app.get("/work/")
    async def work_ui():
        return FileResponse(ADMIN_DIR / "work.html")


def run() -> None:
    uvicorn.run(
        "am_mcp_hub.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
