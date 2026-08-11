"""Read laptop ~/.asrax/chat-memory for hub History UI (mounted as LAPTOP_ASRAX_DIR).

User-specific vault stays on the laptop mount; hub only reads locally (no upload).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")
_PREVIEW_CHARS = 240
_SOURCES_TTL_SEC = 30.0
_LIST_TTL_SEC = 15.0
_sources_cache: dict[str, tuple[float, float, list[dict[str, Any]]]] = {}
_list_cache: dict[tuple[Any, ...], tuple[float, float, list[dict[str, Any]]]] = {}


def chat_memory_root(settings: HubSettings) -> Path:
    return Path(settings.laptop_asrax_dir).expanduser() / "chat-memory"


def _index_path(settings: HubSettings) -> Path:
    return chat_memory_root(settings) / "index.sqlite"


def _safe_filename(conversation_id: str) -> str:
    return _SAFE.sub("_", conversation_id).strip("._") or "conversation"


def _index_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def clear_chat_caches() -> None:
    _sources_cache.clear()
    _list_cache.clear()


def distinct_sources(settings: HubSettings) -> list[dict[str, Any]]:
    path = _index_path(settings)
    if not path.is_file():
        return []
    key = str(path)
    mtime = _index_mtime(path)
    now = time.monotonic()
    hit = _sources_cache.get(key)
    if hit is not None:
        expires_at, cached_mtime, value = hit
        if expires_at > now and cached_mtime == mtime:
            return value
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT source, COUNT(*) AS n FROM conversations GROUP BY source ORDER BY n DESC, source ASC"
        ).fetchall()
        value = [{"source": str(r["source"]), "count": int(r["n"])} for r in rows]
    finally:
        conn.close()
    _sources_cache[key] = (now + _SOURCES_TTL_SEC, mtime, value)
    return value


def list_conversations(
    settings: HubSettings,
    *,
    limit: int = 50,
    offset: int = 0,
    source: str | None = None,
    profile_id: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """List metadata only; never SELECT body (stays on laptop vault, unread for list)."""
    path = _index_path(settings)
    if not path.is_file():
        return []
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    mtime = _index_mtime(path)
    cache_key = (
        str(path),
        mtime,
        limit,
        offset,
        source or "",
        profile_id or "",
        (query or "").strip(),
    )
    now = time.monotonic()
    hit = _list_cache.get(cache_key)
    if hit is not None:
        expires_at, cached_mtime, value = hit
        if expires_at > now and cached_mtime == mtime:
            return value

    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if query and query.strip():
            q = " ".join(f'"{t}"' if any(c in t for c in "-:@/.") else t for t in query.split() if t)
            clauses = ["conversations_fts MATCH ?"]
            params: list[Any] = [q]
            if source:
                clauses.append("conversations.source = ?")
                params.append(source)
            if profile_id:
                clauses.append("conversations.profile_id = ?")
                params.append(profile_id)
            params.extend([limit, offset])
            sql = f"""
                SELECT conversations.id, conversations.source, conversations.profile_id,
                       conversations.machine_id, conversations.title,
                       snippet(conversations_fts, 2, '', '', '…', 32) AS snip,
                       conversations.updated_at, conversations.created_at
                FROM conversations_fts
                JOIN conversations ON conversations.id = conversations_fts.id
                WHERE {' AND '.join(clauses)}
                ORDER BY rank
                LIMIT ? OFFSET ?
            """
            rows = conn.execute(sql, params).fetchall()
        else:
            clauses = ["1=1"]
            params: list[Any] = []
            if source:
                clauses.append("source = ?")
                params.append(source)
            if profile_id:
                clauses.append("profile_id = ?")
                params.append(profile_id)
            params.extend([limit, offset])
            rows = conn.execute(
                f"""
                SELECT id, source, profile_id, machine_id, title, updated_at, created_at
                FROM conversations
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(updated_at, created_at, '') DESC, title ASC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            title = str(r["title"] or "")
            snip = ""
            try:
                snip = str(r["snip"] or "")
            except (IndexError, KeyError):
                snip = ""
            preview = (snip or title)[:_PREVIEW_CHARS]
            out.append(
                {
                    "id": str(r["id"]),
                    "source": str(r["source"]),
                    "profile_id": str(r["profile_id"]),
                    "machine_id": str(r["machine_id"]),
                    "title": title,
                    "preview": preview,
                    "updated_at": r["updated_at"],
                    "created_at": r["created_at"],
                }
            )
        _list_cache[cache_key] = (now + _LIST_TTL_SEC, mtime, out)
        return out
    finally:
        conn.close()


def get_conversation(settings: HubSettings, conversation_id: str) -> dict[str, Any] | None:
    """Load one chat from laptop normalized/*.jsonl only (no vault upload)."""
    root = chat_memory_root(settings)
    path = root / "normalized" / f"{_safe_filename(conversation_id)}.jsonl"
    if path.is_file():
        line = path.read_text(encoding="utf-8").strip().splitlines()[0]
        data = json.loads(line)
        return data if isinstance(data, dict) else None
    index = _index_path(settings)
    if not index.is_file():
        return None
    conn = sqlite3.connect(f"file:{index.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id FROM conversations WHERE id = ? LIMIT 1",
            (conversation_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return None
