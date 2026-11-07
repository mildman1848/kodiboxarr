"""Source-agnostic, read-only boundary for Vavoo catalog candidates.

The bundled Kodi cache envelope is compressed JSON with ``value.channels``;
its per-channel schema is not available in this repository. Callers must pass
records extracted by a verified source adapter. This module deliberately does
not guess that schema or persist/import anything.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Iterable

from .models import PlaylistEntry
from .vavoo_cache import read_cache

PROVIDER = "vavoo"
_URL_OR_SECRET = re.compile(r"(?i)(?:https?|rtmp)://|(?:token|sig|signature|auth)=")


def _key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def records_from_cache(payload: Any) -> list[Any]:
    """Adapt KodiboxTV's verified ``value.channels`` cache envelope.

    The source records contain ``name``, ``group`` and a playback ``url``.
    URLs are deliberately discarded: they can expire or contain credentials.
    Stable candidate identity is derived from the normalized display name and
    group because the source format has no channel ID.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("value"), dict):
        raise ValueError("unexpected KodiboxTV Vavoo cache envelope")
    channels = payload["value"].get("channels")
    if not isinstance(channels, list):
        raise ValueError("KodiboxTV Vavoo cache has no channels list")
    records: list[Any] = []
    for item in channels:
        if not isinstance(item, dict):
            records.append(item)
            continue
        name = item.get("name")
        group = item.get("group", "")
        if not isinstance(name, str) or not isinstance(group, str):
            records.append({"name": name, "group": group})
            continue
        identity_source = f"{_key(group)}\0{_key(name)}"
        identity = hashlib.sha256(identity_source.encode("utf-8")).hexdigest()
        records.append({"name": name, "group": group, "identity": identity})
    return records


def preview_cache(path: Any) -> dict[str, Any]:
    """Read a compressed KodiboxTV cache and return a sanitized preview."""
    return preview_candidates(records_from_cache(read_cache(path)))


def playlist_entries_from_cache(
    path: Any,
    *,
    groups: set[str] | None = None,
    limit: int = 100,
) -> list[PlaylistEntry]:
    """Build a bounded, group-filtered M3U batch without exposing source URLs."""
    limit = max(0, min(int(limit), 100))
    if not limit:
        return []
    entries = []
    records = records_from_cache(read_cache(path))
    if groups:
        allowed_groups = {_key(group) for group in groups}
        records = [record for record in records if isinstance(record, dict) and _key(str(record.get("group", ""))) in allowed_groups]
    preview = preview_candidates(records)
    for item in preview["changes"][:limit]:
        identity = item["identity"]
        group = item["group"]
        entries.append(PlaylistEntry(
            name=item["name"],
            url="",
            attrs={"tvg-id": f"vavoo:{identity}", "group-title": group or "Vavoo"},
            kodibox_name=identity,
            source="kodiboxtv_catalog",
        ))
    return entries


def preview_candidates(records: Iterable[Any]) -> dict[str, Any]:
    """Return sanitized candidate groups and decisions; never include URLs.

    Adapter boundary record contract: mappings with non-empty ``name`` and
    optional ``group`` and ``identity`` strings. Identity is provider-local.
    """
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    rejected = 0
    duplicates = 0
    seen: set[tuple[str, str]] = set()
    total = 0
    for record in records:
        total += 1
        if not isinstance(record, dict):
            rejected += 1
            continue
        name, group, identity = record.get("name"), record.get("group", ""), record.get("identity", "")
        if (not isinstance(name, str) or not name.strip() or
                not isinstance(group, str) or not isinstance(identity, str)):
            rejected += 1
            continue
        name = re.sub(r"\s+", " ", name).strip()
        group = re.sub(r"\s+", " ", group).strip()
        if _URL_OR_SECRET.search(name) or _URL_OR_SECRET.search(group):
            rejected += 1
            continue
        provider_identity = _key(identity or name)
        dedup_key = (PROVIDER, provider_identity)
        if dedup_key in seen:
            duplicates += 1
            continue
        seen.add(dedup_key)
        groups[group].append({"provider": PROVIDER, "identity": provider_identity, "name": name})
    return {
        "mode": "read_only_preview",
        "writes_performed": False,
        "counts": {"input": total, "candidates": len(seen), "duplicates": duplicates, "malformed": rejected},
        "groups": {
            key: {"count": len(values), "sample": values[:5]}
            for key, values in sorted(groups.items())
        },
        "changes": [
            {"action": "candidate", "group": key, **item}
            for key in sorted(groups)
            for item in groups[key]
        ][:100],
        "truncated": len(seen) > 100,
    }
