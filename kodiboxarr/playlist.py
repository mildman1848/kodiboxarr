from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from dataclasses import replace
from typing import Dict, Iterable, List
from urllib.parse import parse_qs, urlparse

from .models import PlaylistEntry

ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')
PSEUDO_HOST = "kodiboxarr.invalid"


def parse_extinf(line: str) -> tuple[Dict[str, str], str]:
    if not line.startswith("#EXTINF"):
        raise ValueError("not an EXTINF line")
    head, _, name = line.partition(",")
    attrs = {key: value for key, value in ATTR_RE.findall(head)}
    return attrs, name.strip()


def kodibox_name_from_plugin_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "plugin" or parsed.netloc != "plugin.video.kodiboxtv":
        return ""
    query = parse_qs(parsed.query)
    return (query.get("name") or [""])[0].strip()


def parse_m3u(text: str) -> List[PlaylistEntry]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    entries: List[PlaylistEntry] = []
    pending = None
    for line in lines:
        if line.startswith("#EXTINF"):
            pending = parse_extinf(line)
            continue
        if line.startswith("#"):
            continue
        if pending is None:
            continue
        attrs, name = pending
        entries.append(
            PlaylistEntry(
                name=name,
                url=line,
                attrs=attrs,
                kodibox_name=kodibox_name_from_plugin_url(line),
            )
        )
        pending = None
    return entries


def assign_source_variants(entries: Iterable[PlaylistEntry]) -> List[PlaylistEntry]:
    """Keep distinct source URLs of one service apart; drop only exact duplicate URLs.

    Variant 0 keeps the legacy placeholder bytes. Later distinct URLs get a stable
    ordinal (playlist order). The URL itself is never stored, since it may be signed.
    """
    seen: Dict[tuple, List[str]] = {}
    result: List[PlaylistEntry] = []
    for entry in entries:
        urls = seen.setdefault((entry.identity, entry.name, entry.group, entry.kodibox_name, entry.source), [])
        if entry.url and entry.url in urls:
            continue
        variant = len(urls)
        urls.append(entry.url)
        result.append(replace(entry, variant=variant) if variant else entry)
    return result


def parse_m3u_file(path: Path) -> List[PlaylistEntry]:
    return parse_m3u(Path(path).read_text(encoding="utf-8", errors="replace"))


def b64url_json(payload: Dict[str, str]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def unb64url_json(value: str) -> Dict[str, str]:
    padded = value + ("=" * (-len(value) % 4))
    return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))


def placeholder_url(entry: PlaylistEntry, provider: str = "vavoo") -> str:
    payload = {
        "provider": provider,
        "identity": entry.identity,
        "name": entry.name,
        "kodibox_name": entry.kodibox_name,
        "group": entry.group,
    }
    if entry.source:
        payload["source"] = entry.source
    if entry.variant:
        payload["variant"] = entry.variant
    return f"http://{PSEUDO_HOST}/{provider}/{b64url_json(payload)}"


def is_placeholder_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.netloc == PSEUDO_HOST


def render_dispatcharr_m3u(entries: Iterable[PlaylistEntry], provider: str = "vavoo") -> str:
    lines = ["#EXTM3U"]
    for entry in entries:
        attrs = dict(entry.attrs)
        attr_text = " ".join(f'{k}="{_attr(v)}"' for k, v in attrs.items() if v)
        suffix = f" {attr_text}" if attr_text else ""
        lines.append(f"#EXTINF:-1{suffix},{_attr(entry.name)}")
        lines.append(placeholder_url(entry, provider=provider))
    return "\n".join(lines) + "\n"


def _attr(value: str) -> str:
    return (value or "").replace('"', "").replace("\n", " ").replace("\r", " ").strip()
