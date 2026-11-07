from __future__ import annotations

import json
import logging
import zlib
from pathlib import Path

from kodiboxarr import sync
from kodiboxarr.playlist import parse_m3u, unb64url_json
from kodiboxarr.vavoo_cache import KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH


class Snapshot:
    def to_dict(self):
        return {
            "build": {"version": "fixture"},
            "build_zip_sha256": "fixture",
            "kodiboxtv_version": "fixture",
            "playlist_sha256": "fixture",
            "channel_count": 1,
            "mapped_tvg_id_count": 1,
            "epg": {"url": "https://example.invalid/epg.xml"},
            "channel_identities": ["base"],
            "vavoo_cache_hash": "fixture",
            "vavoo_raw_channels": 3,
        }


def _setup_build_tree(root: Path) -> None:
    playlist = root / "userdata/addon_data/pvr.iptvsimple/providers/playlist.m3u"
    playlist.parent.mkdir(parents=True)
    playlist.write_text(
        '#EXTM3U\n#EXTINF:-1 tvg-id="base" group-title="Base",Base Channel\nplugin://plugin.video.kodiboxtv/?name=Base\n',
        encoding="utf-8",
    )
    cache_path = root / KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH
    cache_path.parent.mkdir(parents=True)
    cache = {
        "value": {
            "channels": [
                {"name": "World News", "group": "News", "url": "fixture-url-news"},
                {"name": "World News", "group": "Regional", "url": "fixture-url-regional"},
            ]
        }
    }
    cache_path.write_bytes(zlib.compress(json.dumps(cache).encode("utf-8")))


def test_sync_keeps_vavoo_catalog_opt_in_and_limited_to_selected_groups(tmp_path, monkeypatch):
    build_root = tmp_path / "build"
    build_root.mkdir()
    _setup_build_tree(build_root)
    monkeypatch.setattr(
        sync,
        "prepare_build",
        lambda _settings, _logger: {"build_root": str(build_root), "build_zip": str(tmp_path / "build.zip"), "manifest_xml": "fixture"},
    )
    monkeypatch.setattr(sync, "build_snapshot", lambda **_kwargs: Snapshot())
    monkeypatch.setattr(sync, "read_json", lambda _path: None)
    monkeypatch.setattr(sync, "atomic_write_json", lambda *_args: None)

    default_plan = sync.create_plan({}, logging.getLogger("test"))
    assert default_plan["diff"]["vavoo_catalog_candidates"] == 0
    assert len(parse_m3u(default_plan["generated_m3u"])) == 1

    selected_plan = sync.create_plan(
        {
            "include_vavoo_catalog": True,
            "vavoo_catalog_groups": "Regional",
            "vavoo_catalog_import_limit": 1,
        },
        logging.getLogger("test"),
    )
    entries = parse_m3u(selected_plan["generated_m3u"])
    assert selected_plan["diff"]["vavoo_catalog_candidates"] == 1
    assert selected_plan["diff"]["vavoo_catalog_groups"] == ["Regional"]
    assert len(entries) == 2
    payload = unb64url_json(entries[-1].url.rsplit("/", 1)[-1])
    assert payload["source"] == "kodiboxtv_catalog"
    assert payload["group"] == "Regional"
    assert "fixture-url" not in selected_plan["generated_m3u"]


def test_sync_blocks_catalog_import_without_selected_groups(tmp_path, monkeypatch):
    build_root = tmp_path / "build"
    build_root.mkdir()
    _setup_build_tree(build_root)
    monkeypatch.setattr(
        sync,
        "prepare_build",
        lambda _settings, _logger: {"build_root": str(build_root), "build_zip": str(tmp_path / "build.zip"), "manifest_xml": "fixture"},
    )
    monkeypatch.setattr(sync, "build_snapshot", lambda **_kwargs: Snapshot())
    monkeypatch.setattr(sync, "read_json", lambda _path: None)
    monkeypatch.setattr(sync, "atomic_write_json", lambda *_args: None)

    plan = sync.create_plan(
        {"include_vavoo_catalog": True, "vavoo_catalog_import_limit": 1},
        logging.getLogger("test"),
    )

    assert not plan["diff"]["safe"]
    assert plan["diff"]["vavoo_catalog_candidates"] == 0
    assert "selected groups" in " ".join(plan["diff"]["warnings"])
    assert len(parse_m3u(plan["generated_m3u"])) == 1

    unmatched_plan = sync.create_plan(
        {
            "include_vavoo_catalog": True,
            "vavoo_catalog_groups": "Not a real group",
            "vavoo_catalog_import_limit": 1,
        },
        logging.getLogger("test"),
    )
    assert not unmatched_plan["diff"]["safe"]
    assert any("no importable candidates" in warning for warning in unmatched_plan["diff"]["warnings"])
    assert len(parse_m3u(unmatched_plan["generated_m3u"])) == 1
