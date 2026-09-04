"""Local SQLite index for asrax catalog list/filter (laptop mount only)."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services import laptop_catalog as catalog

_PRIVACY = "laptop-local"

_TTL_SEC = 20.0
_cache: dict[str, tuple[float, float, list[dict[str, Any]]]] = {}


def index_path(settings: HubSettings) -> Path:
    return Path(settings.laptop_asrax_dir).expanduser() / "catalog-index.sqlite"


def _connect(settings: HubSettings) -> sqlite3.Connection:
    path = index_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
          kind TEXT NOT NULL,
          id TEXT NOT NULL,
          rel_or_name TEXT,
          owner TEXT,
          tags TEXT,
          always_apply INTEGER,
          readonly INTEGER,
          profile_hint TEXT,
          mtime REAL,
          preview TEXT,
          PRIMARY KEY (kind, id)
        )
        """
    )
    return conn


def rebuild(settings: HubSettings) -> int:
    rows: list[tuple[Any, ...]] = []
    for item in catalog.list_skills(settings):
        rows.append(
            (
                "skills",
                item["name"],
                item["name"],
                item.get("owner"),
                ",".join(item.get("tags") or []),
                None,
                None,
                None,
                item.get("mtime"),
                (item.get("description") or "")[:400],
            )
        )
    for item in catalog.list_rules(settings):
        aa = item.get("always_apply")
        rows.append(
            (
                "rules",
                item["rel"],
                item["rel"],
                item.get("owner"),
                "",
                1 if aa is True else (0 if aa is False else None),
                None,
                None,
                item.get("mtime"),
                (item.get("description") or "")[:400],
            )
        )
    for item in catalog.list_hooks(settings):
        rows.append(
            (
                "hooks",
                item["name"],
                item["name"],
                None,
                "",
                None,
                None,
                None,
                item.get("mtime"),
                (item.get("description") or "")[:400],
            )
        )
    for item in catalog.list_agents(settings):
        rows.append(
            (
                "agents",
                item["rel"],
                item["rel"],
                item.get("owner"),
                "",
                None,
                1 if item.get("readonly") else 0,
                item.get("profile_hint"),
                item.get("mtime"),
                (item.get("description") or item.get("preview") or "")[:400],
            )
        )
    conn = _connect(settings)
    try:
        conn.execute("DELETE FROM entries")
        conn.executemany(
            """
            INSERT INTO entries(kind, id, rel_or_name, owner, tags, always_apply, readonly, profile_hint, mtime, preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    _cache.clear()
    return len(rows)


def _dir_watermark(settings: HubSettings) -> float:
    home = Path(settings.laptop_asrax_dir).expanduser()
    best = 0.0
    for name in ("skills", "rules", "hooks", "agents"):
        root = home / name
        try:
            if root.is_dir():
                best = max(best, root.stat().st_mtime)
        except OSError:
            continue
    return best


def query(
    settings: HubSettings,
    *,
    kind: str,
    q: str | None = None,
    owner: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    wm = _dir_watermark(settings)
    cache_key = f"{kind}|{q}|{owner}|{tag}"
    hit = _cache.get(cache_key)
    now = time.monotonic()
    if hit and hit[0] > now and hit[1] >= wm:
        return hit[2]

    path = index_path(settings)
    if not path.is_file():
        rebuild(settings)
    else:
        # stale if watermark newer than db mtime
        try:
            if wm > path.stat().st_mtime:
                rebuild(settings)
        except OSError:
            rebuild(settings)

    conn = _connect(settings)
    try:
        sql = "SELECT kind, id, rel_or_name, owner, tags, always_apply, readonly, profile_hint, mtime, preview FROM entries WHERE kind = ?"
        args: list[Any] = [kind]
        if owner:
            sql += " AND owner = ?"
            args.append(owner)
        if tag:
            sql += " AND instr(',' || tags || ',', ',' || ? || ',') > 0"
            args.append(tag)
        if q and q.strip():
            sql += " AND (rel_or_name LIKE ? OR ifnull(owner,'') LIKE ? OR ifnull(tags,'') LIKE ? OR ifnull(preview,'') LIKE ?)"
            like = f"%{q.strip()}%"
            args.extend([like, like, like, like])
        sql += " ORDER BY rel_or_name"
        cur = conn.execute(sql, args)
        rows = [
            {
                "kind": r["kind"],
                "id": r["id"],
                "rel_or_name": r["rel_or_name"],
                "owner": r["owner"],
                "tags": [t for t in (r["tags"] or "").split(",") if t],
                "always_apply": None if r["always_apply"] is None else bool(r["always_apply"]),
                "readonly": bool(r["readonly"]) if r["readonly"] is not None else None,
                "profile_hint": r["profile_hint"],
                "mtime": r["mtime"],
                "preview": r["preview"],
                "privacy": _PRIVACY,
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
    _cache[cache_key] = (now + _TTL_SEC, wm, rows)
    return rows
