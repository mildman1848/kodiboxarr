from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from .models import EpgInfo


class EpgError(RuntimeError):
    """Raised when pvr.iptvsimple EPG settings cannot be inspected."""


def parse_pvr_settings(text: str) -> EpgInfo:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise EpgError(f"pvr settings are not valid XML: {exc}") from exc
    values = {}
    for setting in root.findall(".//setting"):
        key = setting.attrib.get("id")
        if key:
            values[key] = (setting.text or "").strip()
    url = values.get("epgUrl") or values.get("epgPath") or ""
    ignore_case = values.get("epgIgnoreCaseForChannelIds", "").lower() in {"true", "1", "yes"}
    return EpgInfo(url=url, ignore_case_channel_ids=ignore_case)


def parse_pvr_settings_file(path: Path) -> EpgInfo:
    return parse_pvr_settings(Path(path).read_text(encoding="utf-8", errors="replace"))
