from __future__ import annotations

import sys
import types
from types import SimpleNamespace

from kodiboxarr import sync


class _QS:
    """Just enough of a Django QuerySet for assign_stream_profile_to_linked_channels."""

    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, **kw):
        rows = self.rows
        for key, val in kw.items():
            if key == "id__in":
                rows = [r for r in rows if r.id in set(val)]
            elif key == "stream_profile__isnull":
                rows = [r for r in rows if (r.stream_profile is None) == val]
            elif key == "stream_profile":
                rows = [r for r in rows if r.stream_profile == val]
            elif key == "stream__m3u_account":
                rows = [r for r in rows if r.stream.m3u_account == val]
        return _QS(rows)

    def exclude(self, stream_profile):
        return _QS(r for r in self.rows if r.stream_profile != stream_profile)

    def values_list(self, name, flat=True):
        return _QS(getattr(r, name) for r in self.rows)

    def distinct(self):
        return _QS(dict.fromkeys(self.rows))

    def __iter__(self):
        return iter(self.rows)

    def count(self):
        return len(self.rows)

    def update(self, stream_profile):
        for r in self.rows:
            r.stream_profile = stream_profile
        return len(self.rows)


def _fake_models(monkeypatch, channels, links):
    models = types.ModuleType("apps.channels.models")
    models.Channel = SimpleNamespace(objects=_QS(channels))
    models.ChannelStream = SimpleNamespace(objects=_QS(links))
    for name in ("apps", "apps.channels"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "apps.channels.models", models)


def test_linked_channel_profile_fill_keeps_multi_stream_links_and_user_choice(monkeypatch):
    ours, other = object(), object()
    profile, user_profile = "kodiboxarr", "user-choice"
    empty = SimpleNamespace(id=1, stream_profile=None)
    chosen = SimpleNamespace(id=2, stream_profile=user_profile)
    # Channel order: user-linked foreign stream first, ours second (and vice versa).
    links = [
        SimpleNamespace(channel_id=1, stream=SimpleNamespace(m3u_account=other), order=0),
        SimpleNamespace(channel_id=1, stream=SimpleNamespace(m3u_account=ours), order=1),
        SimpleNamespace(channel_id=2, stream=SimpleNamespace(m3u_account=ours), order=0),
        SimpleNamespace(channel_id=2, stream=SimpleNamespace(m3u_account=other), order=1),
    ]
    before = [(l.channel_id, id(l.stream), l.order) for l in links]
    _fake_models(monkeypatch, [empty, chosen], links)
    monkeypatch.setattr(sync, "install_stream_profile", lambda: (profile, False))

    result = sync.assign_stream_profile_to_linked_channels(account=ours)

    assert result == (profile, False, 2, 1, 1)
    assert empty.stream_profile == profile
    assert chosen.stream_profile == user_profile
    assert [(l.channel_id, id(l.stream), l.order) for l in links] == before
