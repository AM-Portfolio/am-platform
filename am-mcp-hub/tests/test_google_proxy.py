from __future__ import annotations

from am_mcp_hub.api.google_proxy import _sse_to_json_body


def test_sse_to_json_unwraps_message_event():
    raw = (
        b'event: message\n'
        b'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
    )
    out = _sse_to_json_body(raw)
    assert out is not None
    assert b'"ok":true' in out


def test_sse_to_json_empty():
    assert _sse_to_json_body(b"") is None
    assert _sse_to_json_body(b"event: done\ndata: {}\n\n") is None
