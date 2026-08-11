from __future__ import annotations

import json
import time
from pathlib import Path

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.inspect_report import load_inspect_report, merge_probe_result, tool_counts_by_name


def _settings(tmp_path: Path) -> HubSettings:
    asrax = tmp_path / "asrax"
    am = tmp_path / "am"
    creds = tmp_path / "creds"
    asrax.mkdir()
    am.mkdir()
    creds.mkdir()
    return HubSettings(
        laptop_asrax_dir=str(asrax),
        laptop_am_dir=str(am),
        local_creds_dir=str(creds),
    )


def test_load_merges_partial_local_creds_over_full_asrax(tmp_path: Path):
    settings = _settings(tmp_path)
    full = {
        "ok": 2,
        "total": 2,
        "results": [
            {"name": "github", "ok": True, "tools": 44, "error": "", "tool_names": ["a"]},
            {"name": "vault", "ok": True, "tools": 10, "error": "", "tool_names": ["b"]},
        ],
    }
    asrax_path = Path(settings.laptop_asrax_dir) / "mcp-inspect-all-report.json"
    asrax_path.write_text(json.dumps(full), encoding="utf-8")
    time.sleep(0.05)
    stub = {
        "ok": 1,
        "total": 1,
        "results": [
            {"name": "vault", "ok": True, "tools": 16, "error": "", "tool_names": ["c"]},
        ],
    }
    (Path(settings.local_creds_dir) / "mcp-inspect-all-report.json").write_text(
        json.dumps(stub), encoding="utf-8"
    )

    report = load_inspect_report(settings)
    assert report is not None
    assert report["total"] == 2
    by = tool_counts_by_name(report)
    assert by["github"]["ok"] is True
    assert by["github"]["tools"] == 44
    assert by["vault"]["tools"] == 16


def test_merge_probe_seeds_from_full_report(tmp_path: Path):
    settings = _settings(tmp_path)
    full = {
        "ok": 1,
        "total": 1,
        "results": [
            {"name": "github", "ok": True, "tools": 44, "error": "", "tool_names": ["a"]},
        ],
    }
    (Path(settings.laptop_asrax_dir) / "mcp-inspect-all-report.json").write_text(
        json.dumps(full), encoding="utf-8"
    )
    written = merge_probe_result(
        {"name": "vault", "ok": True, "tools": 16, "tool_names": ["x"], "error": ""},
        settings,
    )
    assert written
    data = json.loads(Path(written[0]).read_text(encoding="utf-8"))
    names = {r["name"] for r in data["results"]}
    assert names == {"github", "vault"}
    assert data["total"] == 2
