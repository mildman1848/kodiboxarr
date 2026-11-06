from __future__ import annotations

from pathlib import Path

from .build_source import addon_version, parse_manifest, sha256_file
from .epg import parse_pvr_settings_file
from .models import Snapshot
from .playlist import parse_m3u_file
from .vavoo_cache import KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH, cache_summary


def build_snapshot(build_root: Path, build_zip: Path, manifest_xml: str, manifest_url: str = "") -> Snapshot:
    build_root = Path(build_root)
    playlist_path = build_root / "userdata/addon_data/pvr.iptvsimple/providers/playlist.m3u"
    pvr_settings = build_root / "userdata/addon_data/pvr.iptvsimple/instance-settings-1.xml"
    vavoo_cache = build_root / KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH
    entries = parse_m3u_file(playlist_path)
    epg = parse_pvr_settings_file(pvr_settings)
    vavoo = cache_summary(vavoo_cache) if vavoo_cache.exists() else {"hash": "", "channels": 0}
    return Snapshot(
        build=parse_manifest(manifest_xml, manifest_url=manifest_url),
        build_zip_sha256=sha256_file(Path(build_zip)),
        kodiboxtv_version=addon_version(build_root),
        playlist_sha256=sha256_file(playlist_path),
        channel_count=len(entries),
        mapped_tvg_id_count=sum(1 for entry in entries if entry.tvg_id),
        epg=epg,
        channel_identities=sorted(entry.identity for entry in entries),
        vavoo_cache_hash=vavoo.get("hash", ""),
        vavoo_raw_channels=int(vavoo.get("channels") or 0),
    )
