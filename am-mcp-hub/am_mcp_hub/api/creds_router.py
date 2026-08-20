"""Local credential admin APIs — files stay on this host only."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from am_mcp_hub.services.auth import AuthContext, require_auth
from am_mcp_hub.services import local_creds as creds

router = APIRouter(prefix="/api/v1/local-creds", tags=["local-creds"])


class CredWrite(BaseModel):
    path: str = Field(min_length=1, max_length=200)
    content: str = Field(default="", max_length=500_000)


class SampleApply(BaseModel):
    sample_id: str
    overwrite: bool = False


@router.get("/status")
async def cred_status(_ctx: AuthContext = Depends(require_auth)):
    return creds.status_summary()


@router.get("/onboard")
async def onboard(_ctx: AuthContext = Depends(require_auth)):
    return {"items": creds.onboard_catalog(), "local_only": True}


@router.get("/files/{path:path}")
async def get_file(path: str, _ctx: AuthContext = Depends(require_auth)):
    try:
        return {"path": path, "content": creds.read_file(path)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/files")
async def put_file(body: CredWrite, _ctx: AuthContext = Depends(require_auth)):
    try:
        info = creds.write_file(body.path, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "file": asdict(info), "local_only": True}


@router.get("/samples")
async def samples(_ctx: AuthContext = Depends(require_auth)):
    return {"samples": creds.list_samples()}


@router.get("/samples/{sample_id:path}")
async def sample_body(sample_id: str, _ctx: AuthContext = Depends(require_auth)):
    try:
        return {"id": sample_id, "content": creds.read_sample(sample_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="sample not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/samples/apply")
async def sample_apply(body: SampleApply, _ctx: AuthContext = Depends(require_auth)):
    try:
        return creds.apply_sample(body.sample_id, overwrite=body.overwrite)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="sample not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload-secret")
async def upload_secret(
    file: UploadFile = File(...),
    _ctx: AuthContext = Depends(require_auth),
):
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=400, detail="file too large")
    try:
        meta = creds.save_secret_upload(file.filename or "upload.bin", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "local_only": True, **meta}


@router.post("/reload")
async def reload_env(_ctx: AuthContext = Depends(require_auth)):
    n = creds.load_into_environ(override=True)
    return {"ok": True, "keys_loaded": n, "local_only": True}
