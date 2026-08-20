"""Prove Google Workspace hub UI + /google/mcp initialize/tools/list."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8130"


def get(path: str, accept: str = "application/json") -> tuple[int, str]:
    req = urllib.request.Request(f"{BASE}{path}", headers={"Accept": accept})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def post_json(path: str, payload: dict, session_id: str | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["mcp-session-id"] = session_id
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        sid = resp.headers.get("mcp-session-id") or ""
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, body, sid


def main() -> int:
    errors: list[str] = []

    try:
        status, html = get("/google/", accept="text/html")
        if status != 200 or "Google Workspace MCP" not in html:
            errors.append(f"/google/ unexpected: status={status}")
        else:
            print("OK /google/ HTML")
    except urllib.error.URLError as exc:
        errors.append(f"/google/ failed: {exc}")

    try:
        status, raw = get("/api/v1/google/status")
        data = json.loads(raw)
        print("OK /api/v1/google/status", "upstream_ok=", data.get("upstream", {}).get("ok"))
        if not data.get("google_inspector_url"):
            errors.append("missing google_inspector_url")
    except Exception as exc:
        errors.append(f"status failed: {exc}")

    try:
        st, init_body, sid = post_json(
            "/google/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "prove-google", "version": "0"},
                },
            },
        )
        if st != 200 or not init_body.get("result"):
            errors.append(f"initialize failed: {init_body}")
        else:
            print("OK initialize", init_body["result"].get("serverInfo"))
        st2, list_body, _ = post_json(
            "/google/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            session_id=sid or None,
        )
        tools = (list_body.get("result") or {}).get("tools") or []
        if st2 != 200 or not tools:
            errors.append(f"tools/list failed or empty: {list_body}")
        else:
            names = [t.get("name") for t in tools[:12]]
            print(f"OK tools/list count={len(tools)} sample={names}")
    except Exception as exc:
        errors.append(f"/google/mcp failed: {exc}")

    if errors:
        print("FAIL")
        for e in errors:
            print(" -", e)
        return 1
    print("PASS google workspace hub UI + mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
