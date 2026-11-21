from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import Mock

from kodiboxarr import sync


def test_sync_to_dispatcharr_never_creates_channels_or_touches_epg_mappings(monkeypatch):
    """Channel creation and EPG-data assignment live only in build_channel_plan
    (gated behind an explicit apply=True plugin action). The normal
    sync_to_dispatcharr path must never reach it, per ROADMAP.md #9.
    """
    plan = {
        "snapshot": {"channel_count": 1, "epg": {"url": "https://example.invalid/epg.xml"}},
        "diff": {"safe": True},
        "generated_m3u": "#EXTM3U\n",
    }
    account = SimpleNamespace(id=1)
    epg_source = SimpleNamespace(id=2)
    profile = SimpleNamespace(id=3)

    monkeypatch.setattr(sync, "create_plan", lambda _settings, _logger: plan)
    monkeypatch.setattr(sync, "write_m3u", lambda _content: "/fake/kodiboxarr-main.m3u")
    monkeypatch.setattr(sync, "upsert_account", lambda *_args: account)
    monkeypatch.setattr(sync, "upsert_epg_source", lambda _snapshot: epg_source)
    monkeypatch.setattr(sync, "request_reparse", lambda _account_id: None)
    monkeypatch.setattr(sync, "request_epg_refresh", lambda _source_id: None)
    monkeypatch.setattr(sync, "assign_stream_profile_to_account_streams", lambda _account: (profile, False, 5, 5))
    monkeypatch.setattr(sync, "assign_stream_profile_to_linked_channels", lambda _account: (profile, False, 3, 3, 3))
    monkeypatch.setattr(sync, "atomic_write_json", lambda *_args: None)
    build_channel_plan = Mock(side_effect=AssertionError("sync_to_dispatcharr must not create channels"))
    monkeypatch.setattr(sync, "build_channel_plan", build_channel_plan)

    result = sync.sync_to_dispatcharr({}, logging.getLogger("test"), dry_run=False)

    assert result["status"] == "ok"
    build_channel_plan.assert_not_called()
