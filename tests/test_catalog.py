from __future__ import annotations

import json
import zlib
from pathlib import Path

from kodiboxarr.catalog import preview_cache, preview_candidates, records_from_cache
from plugin import Plugin

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_catalog_fixture_groups_provider_candidates():
    result = preview_candidates(load_fixture("catalog_valid.json"))
    assert result["counts"] == {"input": 2, "candidates": 2, "duplicates": 0, "malformed": 0}
    assert set(result["groups"]) == {"News", "Sports"}
    assert all(item["provider"] == "vavoo" for item in result["changes"])


def test_duplicate_catalog_records_deduplicate_stably_by_identity():
    result = preview_candidates(load_fixture("catalog_duplicates.json"))
    assert result["counts"] == {"input": 3, "candidates": 1, "duplicates": 2, "malformed": 0}
    assert result["changes"][0]["identity"] == "channel-1"


def test_malformed_catalog_entries_are_rejected():
    result = preview_candidates(load_fixture("catalog_malformed.json"))
    assert result["counts"] == {"input": 3, "candidates": 1, "duplicates": 0, "malformed": 2}


def test_empty_catalog_is_valid():
    result = preview_candidates(load_fixture("catalog_empty.json"))
    assert result["counts"] == {"input": 0, "candidates": 0, "duplicates": 0, "malformed": 0}
    assert result["groups"] == {}
    assert result["changes"] == []


def test_kodiboxtv_cache_adapter_preserves_groups_and_discards_urls():
    records = records_from_cache(load_fixture("kodiboxtv_vavoo_cache.json"))
    result = preview_candidates(records)

    assert result["counts"] == {"input": 4, "candidates": 2, "duplicates": 1, "malformed": 1}
    assert set(result["groups"]) == {"News", "Regional"}
    assert result["groups"]["News"]["count"] == 1
    assert result["groups"]["Regional"]["count"] == 1
    assert "fixture-url" not in json.dumps(result)


def test_plugin_dry_run_reads_compressed_cache_without_dispatcharr_writes(tmp_path, monkeypatch):
    cache_payload = load_fixture("kodiboxtv_vavoo_cache.json")
    cache_path = tmp_path / "vav_channels"
    cache_path.write_bytes(zlib.compress(json.dumps(cache_payload).encode("utf-8")))
    monkeypatch.setattr("plugin.VAVOO_CACHE_PATH", cache_path)

    result = Plugin().run("dry_run_vavoo_catalog", {}, {})
    serialized = json.dumps(result)

    assert result["status"] == "ok"
    assert result["writes_performed"] is False
    assert result["counts"]["candidates"] == 2
    assert "fixture-url" not in serialized


def test_preview_cache_rejects_unknown_cache_envelope(tmp_path):
    cache_path = tmp_path / "invalid-cache"
    cache_path.write_bytes(zlib.compress(b"{}"))
    try:
        preview_cache(cache_path)
    except ValueError as exc:
        assert "cache envelope" in str(exc)
    else:
        raise AssertionError("unexpected cache envelope should be rejected")
