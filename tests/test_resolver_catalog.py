from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

import resolver


def _write_cache(path: Path, channels: list[dict[str, str]]) -> None:
    payload = {"value": {"channels": channels}}
    path.write_bytes(zlib.compress(json.dumps(payload).encode("utf-8")))


def test_resolver_uses_exact_group_and_name_for_kodiboxtv_catalog(tmp_path, monkeypatch):
    cache_path = tmp_path / "vav_channels"
    _write_cache(
        cache_path,
        [
            {"name": "World News", "group": "News", "url": "https://vavoo.to/fixture/news"},
            {"name": "World News", "group": "Regional", "url": "https://vavoo.to/fixture/regional-1"},
            {"name": " world  news ", "group": "regional", "url": "https://vavoo.to/fixture/regional-2"},
            {"name": "Other", "group": "Regional", "url": "https://vavoo.to/fixture/other"},
            {"name": "World News", "group": "Regional", "url": "https://evil.invalid/fixture"},
        ],
    )
    monkeypatch.setattr(resolver, "KODIBOXTV_CACHE_PATH", cache_path)

    candidates = resolver.list_vavoo_candidates(
        {"source": "kodiboxtv_catalog", "name": "World News", "group": "Regional"}
    )

    assert candidates == [
        "https://vavoo.to/fixture/regional-1",
        "https://vavoo.to/fixture/regional-2",
    ]


def test_kodiboxtv_resolver_fails_closed_on_missing_exact_candidate(tmp_path):
    cache_path = tmp_path / "vav_channels"
    _write_cache(cache_path, [{"name": "World News", "group": "News", "url": "https://evil.invalid/fixture"}])

    with pytest.raises(KeyError, match="no exact KodiboxTV"):
        resolver.load_kodiboxtv_vavoo_candidates(
            {"name": "World News", "group": "News"},
            cache_path,
        )
