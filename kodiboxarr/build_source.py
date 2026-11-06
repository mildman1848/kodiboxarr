from __future__ import annotations

import hashlib
import re
import urllib.request
import zipfile
from pathlib import Path

from .models import BuildInfo

DEFAULT_MANIFEST_URL = "https://raw.githubusercontent.com/kodibox32/kodibox/refs/heads/master/builds64.xml"
DEFAULT_BUILD_URL = "https://github.com/kodibox32/kodibox/releases/download/Kodibox64/kodibox64.zip"


class BuildSourceError(RuntimeError):
    """Raised when a Kodibox build artifact cannot be inspected."""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_manifest(url: str = DEFAULT_MANIFEST_URL, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Kodiboxarr/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def download_build(build: BuildInfo, target: Path, timeout: int = 180) -> Path:
    """Download a Kodibox build ZIP to a local file."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(build.url, headers={"User-Agent": "Kodiboxarr/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as response, target.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return target


def parse_manifest(xml_text: str, manifest_url: str = "") -> BuildInfo:
    """Parse a Kodibox Wizard manifest, tolerating not-quite-XML URLs.

    The live Kodibox manifest contains unescaped ampersands inside a Dropbox
    URL, so a strict XML parser rejects the whole document. Kodi add-on feeds are
    sometimes like this. Humanity survives somehow. We parse `<build>` blocks
    and their simple child tags with a narrow regex instead.
    """
    blocks = re.findall(r"<build>(.*?)</build>", xml_text, flags=re.S | re.I)
    if not blocks:
        raise BuildSourceError("manifest does not contain a <build> entry")

    def values(block: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for key in ("name", "version", "kodi", "url", "icon", "fanart"):
            match = re.search(rf"<{key}>(.*?)</{key}>", block, flags=re.S | re.I)
            result[key] = (match.group(1).strip() if match else "")
        return result

    candidates = [values(block) for block in blocks]
    selected = next((item for item in candidates if "github.com" in item.get("url", "") and item.get("version")), None)
    if selected is None:
        selected = next((item for item in candidates if item.get("version")), candidates[0])

    url = selected.get("url", "")
    if not url or url == "http://":
        url = DEFAULT_BUILD_URL
    return BuildInfo(
        name=selected.get("name", ""),
        version=selected.get("version", ""),
        kodi=selected.get("kodi", ""),
        url=url,
        icon=selected.get("icon", ""),
        fanart=selected.get("fanart", ""),
        manifest_url=manifest_url,
    )


def addon_version(build_root: Path, addon_id: str = "plugin.video.kodiboxtv") -> str:
    addon_xml = Path(build_root) / "addons" / addon_id / "addon.xml"
    if not addon_xml.exists():
        raise BuildSourceError(f"missing addon.xml for {addon_id}: {addon_xml}")
    text = addon_xml.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'id=["\']%s["\'].*?version=["\']([^"\']+)' % re.escape(addon_id), text, re.S)
    if not match:
        raise BuildSourceError(f"could not read version from {addon_xml}")
    return match.group(1)


def extract_zip(path: Path, target_dir: Path) -> Path:
    if not zipfile.is_zipfile(path):
        raise BuildSourceError(f"not a ZIP archive: {path}")
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        archive.extractall(target_dir)
    return target_dir
