from __future__ import annotations

import resolver
from kodiboxarr.models import PlaylistEntry
from kodiboxarr.playlist import assign_source_variants, render_dispatcharr_m3u, unb64url_json

A = "https://example.invalid/synthetic/a"
B = "https://example.invalid/synthetic/b"


def _entry(url: str) -> PlaylistEntry:
    return PlaylistEntry(name="Same Name", url=url, attrs={"tvg-id": "same.id", "group-title": "G"})


def _payloads(entries):
    m3u = render_dispatcharr_m3u(entries)
    urls = [line for line in m3u.splitlines() if line.startswith("http")]
    return m3u, urls, [unb64url_json(u.rsplit("/", 1)[-1]) for u in urls]


def test_two_source_urls_same_identity_get_distinct_stable_placeholders():
    entries = assign_source_variants([_entry(A), _entry(B)])
    m3u, urls, payloads = _payloads(entries)
    assert len(urls) == 2 and len(set(urls)) == 2
    assert [p.get("variant", 0) for p in payloads] == [0, 1]
    assert urls == _payloads(assign_source_variants([_entry(A), _entry(B)]))[1]  # stable
    assert "synthetic" not in m3u and "example.invalid/" not in m3u  # no source URLs emitted


def test_exact_duplicate_url_is_deduplicated():
    entries = assign_source_variants([_entry(A), _entry(A), _entry(B)])
    assert [e.url for e in entries] == [A, B]
    assert [e.variant for e in entries] == [0, 1]


def test_resolver_maps_variant_to_its_source_candidate(monkeypatch):
    monkeypatch.setattr(
        resolver, "load_kodiboxtv_vavoo_candidates", lambda payload, path=None: ["u0", "u1", "u2"]
    )
    base = {"source": "kodiboxtv_catalog", "name": "n", "group": "g"}
    assert resolver.list_vavoo_candidates(base)[0] == "u0"
    assert resolver.list_vavoo_candidates({**base, "variant": 1}) == ["u1", "u0", "u2"]
    assert resolver.list_vavoo_candidates({**base, "variant": 9})[0] == "u0"  # out of range: unchanged
