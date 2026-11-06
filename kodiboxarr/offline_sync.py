from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .diff import safety_gate, snapshot_diff
from .playlist import parse_m3u_file, render_dispatcharr_m3u
from .snapshot import build_snapshot
from .state import atomic_write_json, read_json


def dry_run_from_extracted_build(build_root: Path, build_zip: Path, manifest_xml: str, output_dir: Path, manifest_url: str = "", max_removed_percent: int = 30) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    snapshot = build_snapshot(build_root, build_zip, manifest_xml, manifest_url=manifest_url)
    current = snapshot.to_dict()
    previous = read_json(output_dir / "state/snapshot.json")
    diff = safety_gate(snapshot_diff(previous, current), max_removed_percent=max_removed_percent)
    entries = parse_m3u_file(Path(build_root) / "userdata/addon_data/pvr.iptvsimple/providers/playlist.m3u")
    m3u = render_dispatcharr_m3u(entries)
    (output_dir / "generated").mkdir(parents=True, exist_ok=True)
    m3u_path = output_dir / "generated/kodiboxarr-main.m3u"
    m3u_path.write_text(m3u, encoding="utf-8")
    atomic_write_json(output_dir / "state/snapshot.current.json", current)
    atomic_write_json(output_dir / "state/diff.current.json", diff)
    return {"snapshot": current, "diff": diff, "m3u_path": str(m3u_path)}


def commit_snapshot(output_dir: Path) -> Path:
    output_dir = Path(output_dir)
    current = read_json(output_dir / "state/snapshot.current.json")
    if current is None:
        raise RuntimeError("no current snapshot exists; run dry-run first")
    return atomic_write_json(output_dir / "state/snapshot.json", current)
