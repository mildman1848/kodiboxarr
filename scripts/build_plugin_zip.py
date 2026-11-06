#!/usr/bin/env python3
"""Build a clean installable Dispatcharr plugin ZIP for Kodiboxarr."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
RUNTIME_FILES = (
    "__init__.py",
    "plugin.py",
    "plugin.json",
    "resolver.py",
)


def main() -> int:
    manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    DIST.mkdir(exist_ok=True)
    output = DIST / f"kodiboxarr-{version}.zip"

    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for rel in RUNTIME_FILES:
            archive.write(ROOT / rel, rel)
        for path in sorted((ROOT / "kodiboxarr").rglob("*.py")):
            if "__pycache__" not in path.parts:
                archive.write(path, str(path.relative_to(ROOT)))

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"ZIP={output}")
    print(f"SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
