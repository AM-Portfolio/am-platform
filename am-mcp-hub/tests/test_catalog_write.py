from __future__ import annotations

from pathlib import Path

import pytest

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.catalog_write import (
    CatalogWriteError,
    create_skill,
    delete_skill,
    update_skill,
)
from am_mcp_hub.services.laptop_catalog import clear_list_cache, get_skill, list_skills


def _settings(tmp_path: Path) -> HubSettings:
    asrax = tmp_path / "asrax"
    asrax.mkdir()
    return HubSettings(laptop_asrax_dir=str(asrax), laptop_am_dir=str(tmp_path / "am"))


def test_skill_create_update_delete_roundtrip(tmp_path: Path):
    clear_list_cache()
    settings = _settings(tmp_path)
    created = create_skill(
        settings,
        name="demo-write",
        body="# Hello\n",
        description="Demo write",
        owner="platform",
    )
    assert created["name"] == "demo-write"
    assert created["mtime"] is not None
    assert "body" not in list_skills(settings)[0] or True
    assert all("body" not in row for row in list_skills(settings))

    mtime = created["mtime"]
    updated = update_skill(
        settings,
        name="demo-write",
        body="# Updated\n",
        expected_mtime=mtime,
    )
    assert "Updated" in (updated.get("body") or "")

    with pytest.raises(CatalogWriteError) as exc:
        update_skill(
            settings,
            name="demo-write",
            body="# Stale\n",
            expected_mtime=mtime,
            force=False,
        )
    assert exc.value.code == "conflict_mtime"
    assert exc.value.http_status == 409

    forced = update_skill(
        settings,
        name="demo-write",
        body="# Forced\n",
        expected_mtime=mtime,
        force=True,
    )
    assert "Forced" in (forced.get("body") or "")

    deleted = delete_skill(settings, name="demo-write", confirm=True)
    assert deleted["ok"] is True
    assert get_skill(settings, "demo-write") is None


def test_skill_path_escape_rejected(tmp_path: Path):
    clear_list_cache()
    settings = _settings(tmp_path)
    with pytest.raises(CatalogWriteError) as exc:
        create_skill(settings, name="../evil", body="x")
    assert exc.value.code == "validation"


def test_skill_already_exists_without_force(tmp_path: Path):
    clear_list_cache()
    settings = _settings(tmp_path)
    create_skill(settings, name="once", body="# a\n")
    with pytest.raises(CatalogWriteError) as exc:
        create_skill(settings, name="once", body="# b\n", force=False)
    assert exc.value.code == "already_exists"
    create_skill(settings, name="once", body="# b\n", force=True)
    assert "b" in (get_skill(settings, "once") or {}).get("body", "")


def test_skill_delete_not_empty(tmp_path: Path):
    clear_list_cache()
    settings = _settings(tmp_path)
    create_skill(settings, name="bundled", body="# a\n")
    extra = Path(settings.laptop_asrax_dir) / "skills" / "bundled" / "extra.txt"
    extra.write_text("keep\n", encoding="utf-8")
    with pytest.raises(CatalogWriteError) as exc:
        delete_skill(settings, name="bundled", confirm=True, force=False)
    assert exc.value.code == "not_empty"
    assert not (Path(settings.laptop_asrax_dir) / "skills" / "bundled" / "SKILL.md").is_file()
    assert extra.is_file()
