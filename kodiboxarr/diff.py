from __future__ import annotations

from typing import Any, Dict


def snapshot_diff(previous: Dict[str, Any] | None, current: Dict[str, Any]) -> Dict[str, Any]:
    if not previous:
        return {"first_run": True, "added": current.get("channel_count", 0), "removed": 0, "changed": [], "safe": True, "warnings": []}
    prev_ids = set(previous.get("channel_identities") or [])
    curr_ids = set(current.get("channel_identities") or [])
    removed = sorted(prev_ids - curr_ids)
    added = sorted(curr_ids - prev_ids)
    changed = []
    for key in ["build_zip_sha256", "kodiboxtv_version", "playlist_sha256", "vavoo_cache_hash"]:
        if previous.get(key) != current.get(key):
            changed.append(key)
    if (previous.get("build") or {}).get("version") != (current.get("build") or {}).get("version"):
        changed.append("build.version")
    if (previous.get("epg") or {}).get("url") != (current.get("epg") or {}).get("url"):
        changed.append("epg.url")
    prev_count = max(1, int(previous.get("channel_count") or len(prev_ids) or 1))
    removed_percent = round((len(removed) / prev_count) * 100, 2)
    warnings = []
    if current.get("channel_count", 0) <= 0:
        warnings.append("current playlist is empty")
    if not (current.get("epg") or {}).get("url"):
        warnings.append("EPG URL is empty")
    return {"first_run": False, "added": len(added), "removed": len(removed), "removed_percent": removed_percent, "changed": changed, "safe": not warnings, "warnings": warnings, "added_sample": added[:20], "removed_sample": removed[:20]}


def safety_gate(diff: Dict[str, Any], max_removed_percent: int = 30) -> Dict[str, Any]:
    warnings = list(diff.get("warnings") or [])
    if not diff.get("first_run") and float(diff.get("removed_percent") or 0) > max_removed_percent:
        warnings.append(f"removed channel percentage exceeds limit: {diff.get('removed_percent')}% > {max_removed_percent}%")
    return {**diff, "safe": not warnings, "warnings": warnings}
