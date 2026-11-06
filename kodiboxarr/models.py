from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class BuildInfo:
    """Metadata read from Kodibox Wizard's build manifest."""

    name: str
    version: str
    kodi: str
    url: str
    icon: str = ""
    fanart: str = ""
    manifest_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlaylistEntry:
    """One entry from Kodibox's PVR Simple playlist."""

    name: str
    url: str
    attrs: Dict[str, str] = field(default_factory=dict)
    kodibox_name: str = ""

    @property
    def identity(self) -> str:
        return self.attrs.get("tvg-id") or self.kodibox_name or self.name

    @property
    def group(self) -> str:
        return self.attrs.get("group-title", "")

    @property
    def logo(self) -> str:
        return self.attrs.get("tvg-logo", "")

    @property
    def tvg_id(self) -> str:
        return self.attrs.get("tvg-id", "")

    @property
    def tvg_name(self) -> str:
        return self.attrs.get("tvg-name", "")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EpgInfo:
    """EPG source metadata from pvr.iptvsimple settings."""

    url: str
    ignore_case_channel_ids: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Snapshot:
    """Stable summary used to detect Kodibox/Vavoo changes."""

    build: BuildInfo
    build_zip_sha256: str
    kodiboxtv_version: str
    playlist_sha256: str
    channel_count: int
    mapped_tvg_id_count: int
    epg: EpgInfo
    channel_identities: List[str]
    vavoo_cache_hash: str = ""
    vavoo_raw_channels: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
