from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

try:
    from .kodiboxarr.build_source import DEFAULT_MANIFEST_URL, fetch_manifest, parse_manifest
    from .kodiboxarr.sync import build_channel_plan, delete_auto_channels, generate_mapping_report, sync_to_dispatcharr
except ImportError:  # Standalone test import, outside Dispatcharr's package loader.
    from kodiboxarr.build_source import DEFAULT_MANIFEST_URL, fetch_manifest, parse_manifest
    from kodiboxarr.sync import build_channel_plan, delete_auto_channels, generate_mapping_report, sync_to_dispatcharr

_MANIFEST_PATH = Path(__file__).with_name("plugin.json")
MANIFEST = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))


class Plugin:
    """Dispatcharr plugin entry point."""

    name = MANIFEST["name"]
    version = MANIFEST["version"]
    description = MANIFEST["description"]
    author = MANIFEST.get("author", "")
    fields = MANIFEST.get("fields", [])
    actions = MANIFEST.get("actions", [])

    def run(self, action: str, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        logger = context.get("logger") or logging.getLogger(__name__)
        settings = _merge_defaults(_settings_from_context_and_params(context, params))
        try:
            if action == "check_build":
                return self._check_build(settings)
            if action == "dry_run_sync":
                return sync_to_dispatcharr(settings, logger, dry_run=True)
            if action == "sync_now":
                return sync_to_dispatcharr(settings, logger, dry_run=False)
            if action == "mapping_report":
                return generate_mapping_report(settings)
            if action == "dry_run_channel_plan":
                return build_channel_plan(settings, apply=False)
            if action == "apply_channel_plan":
                return build_channel_plan(settings, apply=True)
            if action == "dry_run_delete_channels":
                return delete_auto_channels(settings, apply=False)
            if action == "delete_auto_channels":
                return delete_auto_channels(settings, apply=True)
            if action == "assign_profile":
                return self._assign_profile(logger)
            return {"status": "error", "message": f"Unknown action: {action}"}
        except Exception as exc:
            logger.exception("kodiboxarr: action failed")
            return {"status": "error", "message": f"{action} failed: {type(exc).__name__}: {exc}"}

    def stop(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "ok"}

    def _check_build(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        url = settings.get("manifest_url") or DEFAULT_MANIFEST_URL
        xml = fetch_manifest(url)
        build = parse_manifest(xml, manifest_url=url)
        return {
            "status": "ok",
            "message": f"Kodibox build {build.version} for {build.kodi}: {build.url}",
            "build": build.to_dict(),
        }

    def _assign_profile(self, logger) -> Dict[str, Any]:
        try:
            from .kodiboxarr.sync import assign_stream_profile_to_account_streams, assign_stream_profile_to_linked_channels
        except ImportError:  # Standalone test import, outside Dispatcharr's package loader.
            from kodiboxarr.sync import assign_stream_profile_to_account_streams, assign_stream_profile_to_linked_channels

        profile, created, stream_count, changed = assign_stream_profile_to_account_streams()
        _, _, linked_channel_count, channel_changed, channel_profiled_count = assign_stream_profile_to_linked_channels()
        return {
            "status": "ok",
            "message": f"stream profile {'created' if created else 'updated'}; streams assigned {changed}/{stream_count}; linked channels assigned {channel_changed}/{linked_channel_count}: {profile.name}",
            "stream_profile_id": profile.id,
            "stream_count": stream_count,
            "profile_assigned_count": changed,
            "linked_channel_count": linked_channel_count,
            "channel_profile_assigned_count": channel_changed,
            "channel_profiled_count": channel_profiled_count,
        }


def _settings_from_context_and_params(context: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """Merge persisted plugin settings with explicit run-time overrides."""
    merged = dict(context.get("settings") or {})
    params = params or {}
    runtime_settings = params.get("settings") if isinstance(params.get("settings"), dict) else {}
    merged.update(runtime_settings)
    for field in MANIFEST.get("fields", []):
        field_id = field.get("id")
        if field_id in params and field_id not in {"status"}:
            merged[field_id] = params[field_id]
    return merged


def _merge_defaults(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(settings)
    for field in MANIFEST.get("fields", []):
        if "id" in field and "default" in field and field["id"] not in merged:
            merged[field["id"]] = field["default"]
    return merged
