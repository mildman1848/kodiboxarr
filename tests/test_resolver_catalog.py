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


def test_tcp_probe_failure_log_omits_signed_url(monkeypatch, capsys):
    signed = "https://edge.example.invalid/hls/path-secret/index.m3u8?sig=query-secret"
    monkeypatch.setattr(resolver, "list_vavoo_candidates", lambda payload: ["https://vavoo.to/fixture"])
    monkeypatch.setattr(resolver, "resolve_vavoo_link", lambda url: signed)
    monkeypatch.setattr(resolver, "probe_resolved_url", lambda url: False)

    with pytest.raises(RuntimeError, match="all 1 candidates failed"):
        resolver.passthrough_vavoo_payload({"name": "Fixture"}, "ua")

    err = capsys.readouterr().err
    assert "edge.example.invalid" in err
    assert "path-secret" not in err and "query-secret" not in err and "sig=" not in err


def test_resolve_vavoo_link_rejects_malformed_and_unsafe_responses(monkeypatch):
    class Response:
        def __init__(self, data):
            self.data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self.data

    class Requests:
        def __init__(self, data):
            self.data = data

        def post(self, *_args, **_kwargs):
            return Response(self.data)

    monkeypatch.setattr(resolver, "get_auth_signature", lambda: "fixture")
    for data in (
        [{"url": "http://edge.example.invalid/clear"}],
        [{"url": 17}],
        [None],
        {},
    ):
        monkeypatch.setattr(resolver, "requests", Requests(data))
        with pytest.raises(RuntimeError, match="resolve response") as exc_info:
            resolver.resolve_vavoo_link("https://vavoo.to/input-secret")
        assert "input-secret" not in str(exc_info.value)

    monkeypatch.setattr(resolver, "requests", Requests([{"url": "https://edge.example.invalid/signed?sig=secret"}]))
    assert resolver.resolve_vavoo_link("https://vavoo.to/fixture").startswith("https://edge.example.invalid/")

    monkeypatch.setattr(resolver, "requests", Requests([{"url": "https://edge.example.invalid/ok"}]))
    assert resolver.resolve_vavoo_link("https://vavoo.to/fixture") == "https://edge.example.invalid/ok"


def test_shared_candidate_resolver_reports_only_safe_host(monkeypatch):
    signed = "https://edge.example.invalid/hls/private-path?token=private-query"
    monkeypatch.setattr(resolver, "resolve_vavoo_link", lambda _url: signed)
    monkeypatch.setattr(resolver, "probe_resolved_url", lambda _url: False)

    with pytest.raises(RuntimeError) as exc_info:
        resolver.resolve_healthy_vavoo_candidate("https://vavoo.to/fixture")

    assert "edge.example.invalid" in str(exc_info.value)
    assert "private-path" not in str(exc_info.value)
    assert "private-query" not in str(exc_info.value)


def test_resolve_pseudo_url_uses_shared_candidate_resolution(monkeypatch):
    monkeypatch.setattr(resolver, "decode_payload", lambda _url: {"provider": "vavoo", "name": "Fixture"})
    monkeypatch.setattr(resolver, "list_vavoo_candidates", lambda _payload: ["candidate"])
    monkeypatch.setattr(resolver, "resolve_healthy_vavoo_candidate", lambda _url: "https://edge.example.invalid/ok")

    assert resolver.resolve_pseudo_url("https://kodiboxarr.invalid/vavoo/fixture") == "https://edge.example.invalid/ok"
