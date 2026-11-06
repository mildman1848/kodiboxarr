from __future__ import annotations

import json
import zlib
from pathlib import Path
from typing import Any, Dict

KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH = "userdata/addon_data/plugin.video.kodiboxtv/cache/vav_channels"


class VavooCacheError(RuntimeError):
    """Raised when Kodibox's cached Vavoo data cannot be decoded."""


def read_cache(path: Path) -> Dict[str, Any]:
    try:
        data = zlib.decompress(Path(path).read_bytes()).decode("utf-8")
        payload = json.loads(data)
    except Exception as exc:
        raise VavooCacheError(f"could not decode Vavoo cache {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise VavooCacheError(f"Vavoo cache {path} is not an object")
    return payload


def cache_summary(path: Path) -> Dict[str, Any]:
    payload = read_cache(path)
    value = payload.get("value") if isinstance(payload.get("value"), dict) else {}
    channels = value.get("channels") if isinstance(value.get("channels"), list) else []
    return {"sigValidUntil": payload.get("sigValidUntil"), "hash": value.get("hash", ""), "channels": len(channels)}
