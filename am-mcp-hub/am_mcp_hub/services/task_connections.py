"""User-configured runner connections under ~/.asrax/work/connections.json."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.catalog_write import CatalogWriteError, _write_home

_PRIVACY = "laptop-local"
_ID_RE = re.compile(r"^[a-zA-Z0-9._-]+$")
_KINDS = frozenset({"ide", "openai_compatible", "gemini", "anthropic"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(settings: HubSettings) -> Path:
    home = _write_home(settings)
    root = home / "work"
    root.mkdir(parents=True, exist_ok=True)
    return root / "connections.json"


def _default_doc(settings: HubSettings) -> dict[str, Any]:
    return {
        "default_connection_id": "cursor-local",
        "connections": [
            {
                "id": "cursor-local",
                "label": "Cursor (local)",
                "kind": "ide",
                "ide": "cursor",
                "cwd": "",
                "model": "composer-2.5",
                "auth_env": "CURSOR_API_KEY",
                "mcp_url": "http://127.0.0.1:8130/mcp",
                "last_ok_at": None,
                "last_error": "",
            },
            {
                "id": "litellm-org",
                "label": "Org LiteLLM",
                "kind": "openai_compatible",
                "base_url": settings.litellm_url.rstrip("/"),
                "model": "",
                "auth_env": "LITELLM_MASTER_KEY",
                "last_ok_at": None,
                "last_error": "",
            },
            {
                "id": "gemini-default",
                "label": "Gemini",
                "kind": "gemini",
                "model": "gemini-2.5-flash",
                "auth_env": "GEMINI_API_KEY",
                "last_ok_at": None,
                "last_error": "",
            },
            {
                "id": "anthropic-default",
                "label": "Anthropic",
                "kind": "anthropic",
                "model": "claude-sonnet-4-5",
                "auth_env": "ANTHROPIC_API_KEY",
                "last_ok_at": None,
                "last_error": "",
            },
        ],
        "privacy": _PRIVACY,
    }


def load_connections(settings: HubSettings) -> dict[str, Any]:
    path = _path(settings)
    if not path.is_file():
        doc = _default_doc(settings)
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return doc
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        doc = _default_doc(settings)
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return doc
    if not isinstance(doc.get("connections"), list):
        doc["connections"] = []
    doc["privacy"] = _PRIVACY
    return doc


def save_connections(settings: HubSettings, doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    doc["privacy"] = _PRIVACY
    path = _path(settings)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return doc


def list_connections(settings: HubSettings) -> dict[str, Any]:
    doc = load_connections(settings)
    # never echo secrets
    return {
        "default_connection_id": doc.get("default_connection_id") or "",
        "connections": list(doc.get("connections") or []),
        "privacy": _PRIVACY,
    }


def upsert_connection(settings: HubSettings, body: dict[str, Any]) -> dict[str, Any]:
    cid = str(body.get("id") or "").strip()
    if not cid or not _ID_RE.fullmatch(cid):
        raise CatalogWriteError(code="validation", detail="invalid connection id", http_status=400)
    kind = str(body.get("kind") or "").strip()
    if kind not in _KINDS:
        raise CatalogWriteError(code="validation", detail=f"kind must be one of {sorted(_KINDS)}", http_status=400)
    doc = load_connections(settings)
    rows = list(doc.get("connections") or [])
    conn = {
        "id": cid,
        "label": str(body.get("label") or cid).strip(),
        "kind": kind,
        "ide": str(body.get("ide") or ("cursor" if kind == "ide" else "")).strip(),
        "cwd": str(body.get("cwd") or "").strip(),
        "base_url": str(body.get("base_url") or "").strip().rstrip("/"),
        "model": str(body.get("model") or "").strip(),
        "auth_env": str(body.get("auth_env") or "").strip(),
        "mcp_url": str(body.get("mcp_url") or "http://127.0.0.1:8130/mcp").strip(),
        "last_ok_at": None,
        "last_error": "",
    }
    # preserve last_ok if updating same id without retest
    for old in rows:
        if old.get("id") == cid:
            conn["last_ok_at"] = old.get("last_ok_at")
            conn["last_error"] = old.get("last_error") or ""
            break
    rows = [r for r in rows if r.get("id") != cid]
    rows.append(conn)
    doc["connections"] = rows
    if body.get("make_default"):
        doc["default_connection_id"] = cid
    save_connections(settings, doc)
    return {"ok": True, "connection": conn, "privacy": _PRIVACY}


def delete_connection(settings: HubSettings, connection_id: str) -> dict[str, Any]:
    doc = load_connections(settings)
    before = len(doc.get("connections") or [])
    doc["connections"] = [c for c in (doc.get("connections") or []) if c.get("id") != connection_id]
    if doc.get("default_connection_id") == connection_id:
        doc["default_connection_id"] = (doc["connections"][0]["id"] if doc["connections"] else "")
    save_connections(settings, doc)
    return {"ok": True, "deleted": before - len(doc["connections"]), "privacy": _PRIVACY}


def get_connection(settings: HubSettings, connection_id: str) -> dict[str, Any] | None:
    doc = load_connections(settings)
    for c in doc.get("connections") or []:
        if c.get("id") == connection_id:
            return dict(c)
    return None


def resolve_auth(conn: dict[str, Any]) -> str:
    env_name = str(conn.get("auth_env") or "").strip()
    if not env_name:
        return ""
    return (os.environ.get(env_name) or "").strip()


async def test_connection(settings: HubSettings, connection_id: str) -> dict[str, Any]:
    conn = get_connection(settings, connection_id)
    if conn is None:
        raise CatalogWriteError(code="not_found", detail=f"connection not found: {connection_id}", http_status=404)
    kind = conn.get("kind")
    key = resolve_auth(conn)
    models: list[str] = []
    error = ""
    ok = False
    try:
        if kind == "ide":
            if not (conn.get("cwd") or "").strip():
                error = "cwd is required for Cursor IDE connection"
            elif not key:
                error = f"Set {conn.get('auth_env') or 'CURSOR_API_KEY'} in local credentials"
            else:
                ok = True
                # SDK availability checked on host runner; hub only validates config
        elif kind == "openai_compatible":
            base = (conn.get("base_url") or settings.litellm_url).rstrip("/")
            headers = {"Accept": "application/json"}
            if key:
                headers["Authorization"] = f"Bearer {key}"
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get(f"{base}/v1/models", headers=headers)
                if resp.status_code >= 300:
                    error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                else:
                    data = resp.json()
                    for row in data.get("data") or []:
                        mid = row.get("id")
                        if mid:
                            models.append(str(mid))
                    ok = True
        elif kind == "gemini":
            if not key:
                error = "Set GEMINI_API_KEY (or auth_env) in local credentials"
            else:
                model = conn.get("model") or "gemini-2.5-flash"
                url = (
                    f"https://generativelanguage.googleapis.com/v1beta/models/"
                    f"{model}:generateContent?key={key}"
                )
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.post(
                        url,
                        json={"contents": [{"parts": [{"text": "ping"}]}]},
                    )
                    if resp.status_code >= 300:
                        error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    else:
                        ok = True
                        models = [model]
        elif kind == "anthropic":
            if not key:
                error = "Set ANTHROPIC_API_KEY in local credentials"
            else:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    resp = await client.get(
                        "https://api.anthropic.com/v1/models",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                        },
                    )
                    if resp.status_code >= 300:
                        # models endpoint may vary; try messages ping instead
                        error = f"HTTP {resp.status_code}: {resp.text[:160]}"
                        ok = False
                    else:
                        data = resp.json()
                        for row in data.get("data") or []:
                            mid = row.get("id")
                            if mid:
                                models.append(str(mid))
                        ok = True
        else:
            error = f"unsupported kind: {kind}"
    except Exception as exc:  # noqa: BLE001
        error = str(exc)[:300]
        ok = False

    doc = load_connections(settings)
    for c in doc.get("connections") or []:
        if c.get("id") == connection_id:
            c["last_ok_at"] = _now() if ok else None
            c["last_error"] = "" if ok else error
            if models and not c.get("model"):
                c["model"] = models[0]
            break
    save_connections(settings, doc)
    return {
        "ok": ok,
        "connection_id": connection_id,
        "models": models[:80],
        "error": error,
        "privacy": _PRIVACY,
    }
