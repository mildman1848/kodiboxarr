from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_plugin_zip_contains_only_runtime_files(tmp_path):
    subprocess.run([sys.executable, "scripts/build_plugin_zip.py"], cwd=ROOT, check=True)
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    archive_path = ROOT / "dist" / f"kodiboxarr-{manifest['version']}.zip"
    assert archive_path.is_file()

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "plugin.py" in names
        assert "plugin.json" in names
        assert "resolver.py" in names
        assert "kodiboxarr/build_source.py" in names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert not any(name.startswith(("tests/", "dist/", "state/", "extracted/")) for name in names)


def test_plugin_manifest_has_repository_and_license():
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "AGPL-3.0-only"
    assert manifest["repo_url"] == "https://github.com/mildman1848/kodiboxarr"
    assert manifest["help_url"].startswith(manifest["repo_url"])


def test_resolver_url_diagnostics_never_include_signed_path_or_query():
    from resolver import safe_url_host

    url = "https://cdn.example.invalid/live/channel.m3u8?token=private-signature"
    host = safe_url_host(url)
    assert host == "cdn.example.invalid"
    assert "private-signature" not in host
    assert "/live/" not in host
