from __future__ import annotations

from pathlib import Path

from am_mcp_hub.core.config import get_settings
from am_mcp_hub.services import local_creds as creds


def test_local_creds_samples_and_write(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_CREDS_DIR", str(tmp_path / "creds"))
    get_settings.cache_clear()
    copied = creds.ensure_samples_copied()
    assert copied
    samples = creds.list_samples()
    assert any(s["id"].endswith("github.env") for s in samples)
    applied = creds.apply_sample("github.env")
    assert applied["status"] == "written"
    assert (tmp_path / "creds" / "credentials.d" / "github.env").is_file()
    n = creds.load_into_environ()
    assert n >= 0
    st = creds.status_summary()
    assert st["local_only"] is True
    assert st["never_uploaded"] is True
    get_settings.cache_clear()
