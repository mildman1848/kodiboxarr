from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from .build_source import DEFAULT_MANIFEST_URL, download_build, extract_zip, fetch_manifest, parse_manifest
from .diff import safety_gate, snapshot_diff
from .playlist import parse_m3u_file, render_dispatcharr_m3u
from .snapshot import build_snapshot
from .state import atomic_write_json, read_json

DATA_DIR = Path(os.environ.get("KODIBOXARR_DATA_DIR", "/data/kodiboxarr"))
M3U_DIR = Path("/data/uploads/m3us")
ACCOUNT_NAME = "Kodiboxarr: Kodibox TV"
STREAM_PROFILE_NAME = "Kodiboxarr"
MARKER_KEY = "kodiboxarr"


def prepare_build(settings: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """Fetch and extract the current Kodibox build into the data volume."""
    manifest_url = settings.get("manifest_url") or DEFAULT_MANIFEST_URL
    manifest_xml = fetch_manifest(manifest_url)
    build = parse_manifest(manifest_xml, manifest_url=manifest_url)

    downloads = DATA_DIR / "downloads"
    extracted = DATA_DIR / "extracted" / "buildzip"
    reports = DATA_DIR / "reports"
    downloads.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    build_zip = downloads / "kodibox64.zip"
    logger.info("kodiboxarr: downloading Kodibox build %s from %s", build.version, build.url)
    download_build(build, build_zip)

    if extracted.exists():
        # Keep replacement atomic-ish: extract into a sibling and swap. Removing
        # the old tree only after a successful ZIP check prevents a corrupt
        # download from erasing the last usable build.
        tmp_parent = extracted.parent
    else:
        tmp_parent = extracted.parent
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=".buildzip.", dir=tmp_parent))
    try:
        extract_zip(build_zip, tmp_dir)
        if extracted.exists():
            import shutil

            shutil.rmtree(extracted)
        tmp_dir.replace(extracted)
    except Exception:
        import shutil

        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    (reports / "builds64.xml").write_text(manifest_xml, encoding="utf-8")
    return {"build": build.to_dict(), "build_zip": str(build_zip), "build_root": str(extracted), "manifest_xml": manifest_xml}


def write_m3u(content: str) -> Path:
    """Write Kodiboxarr's generated playlist where Dispatcharr reads uploads."""
    M3U_DIR.mkdir(parents=True, exist_ok=True)
    path = M3U_DIR / "kodiboxarr-main.m3u"
    fd, tmp = tempfile.mkstemp(dir=M3U_DIR, prefix=".kodiboxarr-main.", suffix=".m3u")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def create_plan(settings: Dict[str, Any], logger: logging.Logger) -> Dict[str, Any]:
    """Build the current snapshot, generated M3U and safety-gated diff."""
    prepared = prepare_build(settings, logger)
    snapshot = build_snapshot(
        build_root=Path(prepared["build_root"]),
        build_zip=Path(prepared["build_zip"]),
        manifest_xml=prepared["manifest_xml"],
        manifest_url=settings.get("manifest_url") or DEFAULT_MANIFEST_URL,
    )
    current = snapshot.to_dict()
    previous = read_json(DATA_DIR / "state/snapshot.json")
    diff = safety_gate(
        snapshot_diff(previous, current),
        max_removed_percent=int(settings.get("max_removed_percent") or 30),
    )
    entries = parse_m3u_file(Path(prepared["build_root"]) / "userdata/addon_data/pvr.iptvsimple/providers/playlist.m3u")
    generated_m3u = render_dispatcharr_m3u(entries)
    atomic_write_json(DATA_DIR / "state/snapshot.current.json", current)
    atomic_write_json(DATA_DIR / "state/diff.current.json", diff)
    return {"snapshot": current, "diff": diff, "generated_m3u": generated_m3u}


def install_stream_profile():
    """Create the core stream profile that invokes the Kodiboxarr resolver."""
    from core.models import StreamProfile

    resolver_path = Path(__file__).resolve().parents[1] / "resolver.py"
    interpreter = _python_executable()
    profile, created = StreamProfile.objects.get_or_create(
        name=STREAM_PROFILE_NAME,
        defaults={
            "command": interpreter,
            "parameters": f"{resolver_path} {{streamUrl}} {{userAgent}}",
            "is_active": True,
            "locked": False,
        },
    )
    if not created:
        profile.command = interpreter
        profile.parameters = f"{resolver_path} {{streamUrl}} {{userAgent}}"
        profile.is_active = True
        profile.save()
    return profile, created


def assign_stream_profile_to_account_streams(account=None):
    """Assign the Kodiboxarr core StreamProfile to every Kodiboxarr stream.

    Dispatcharr resolves pseudo URLs only if the effective channel StreamProfile
    is our resolver wrapper. Stream-level assignment documents intent and helps
    if Dispatcharr later honors stream profiles directly.
    """
    from apps.channels.models import Stream

    profile, created = install_stream_profile()
    if account is None:
        account = upsert_account_placeholder()
    streams = Stream.objects.filter(m3u_account=account)
    total = streams.count()
    changed = streams.exclude(stream_profile=profile).update(stream_profile=profile)
    return profile, created, total, changed


def assign_stream_profile_to_linked_channels(account=None, overwrite: bool = False):
    """Assign the Kodiboxarr StreamProfile to channels using Kodiboxarr streams.

    Dispatcharr currently has a TODO in Channel.get_stream_profile() and does
    not honor the linked stream's stream_profile. Without this channel-level
    assignment, the live proxy feeds kodiboxarr.invalid directly to ffmpeg.
    By default we only fill empty channel profiles and do not overwrite user
    choices.
    """
    from apps.channels.models import Channel, ChannelStream

    profile, created = install_stream_profile()
    if account is None:
        account = upsert_account_placeholder()
    channel_ids = ChannelStream.objects.filter(stream__m3u_account=account).values_list("channel_id", flat=True).distinct()
    channels = Channel.objects.filter(id__in=channel_ids)
    target = channels if overwrite else channels.filter(stream_profile__isnull=True)
    changed = target.exclude(stream_profile=profile).update(stream_profile=profile)
    return profile, created, channels.count(), changed, channels.filter(stream_profile=profile).count()


def upsert_account_placeholder():
    """Return the marked Kodiboxarr account without changing playlist state."""
    from apps.m3u.models import M3UAccount

    account = M3UAccount.objects.filter(custom_properties__has_key=MARKER_KEY).first()
    if account is None:
        account = M3UAccount.objects.filter(name=ACCOUNT_NAME).first()
    if account is None:
        raise RuntimeError(f"M3U account not found: {ACCOUNT_NAME}")
    return account


def upsert_account(file_path: Path, snapshot: Dict[str, Any], refresh_hours: int = 0):
    from apps.m3u.models import M3UAccount

    account = M3UAccount.objects.filter(custom_properties__has_key=MARKER_KEY).first()
    if account is None:
        account, _ = M3UAccount.objects.get_or_create(
            name=ACCOUNT_NAME,
            defaults={"account_type": M3UAccount.Types.STADNARD},
        )
    account.name = ACCOUNT_NAME
    account.file_path = str(file_path)
    account.server_url = None
    account.account_type = M3UAccount.Types.STADNARD
    account.is_active = True
    account.refresh_interval = max(0, int(refresh_hours or 0))
    props = dict(account.custom_properties or {})
    props[MARKER_KEY] = {
        "source": "kodibox",
        "build_version": (snapshot.get("build") or {}).get("version", ""),
    }
    account.custom_properties = props
    account.save()
    return account


def upsert_epg_source(snapshot: Dict[str, Any]):
    from apps.epg.models import EPGSource

    epg_url = (snapshot.get("epg") or {}).get("url") or ""
    if not epg_url:
        return None
    source = EPGSource.objects.filter(custom_properties__has_key=MARKER_KEY).first()
    if source is None:
        source, _ = EPGSource.objects.get_or_create(
            name="Kodiboxarr: EPG",
            defaults={"source_type": "xmltv"},
        )
    source.name = "Kodiboxarr: EPG"
    source.source_type = "xmltv"
    source.url = epg_url
    source.file_path = None
    source.is_active = True
    source.refresh_interval = 24
    props = dict(source.custom_properties or {})
    props[MARKER_KEY] = {"source": "kodibox", "url": epg_url}
    source.custom_properties = props
    source.save()
    return source


def request_reparse(account_id: int) -> None:
    from apps.m3u.tasks import refresh_single_m3u_account

    refresh_single_m3u_account.delay(account_id)


def request_epg_refresh(source_id: int) -> None:
    from apps.epg.tasks import refresh_epg_data

    refresh_epg_data.delay(source_id)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalise_channel_name(value: str) -> str:
    import re

    value = (value or "").upper().replace("&AMP;", "&")
    value = re.sub(r"\bHD\+?\b", "", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _next_channel_number(used: set, start: int) -> float:
    number = float(start)
    while number in used:
        number += 1.0
    used.add(number)
    return number


def build_channel_plan(settings: Dict[str, Any], apply: bool = False) -> Dict[str, Any]:
    """Plan or apply safe Kodiboxarr channel creation from imported streams.

    The plan is intentionally marker-based: only channels with
    auto_created_by=Kodiboxarr are updated/deleted by later iterations. Manual
    channels are reported as conflicts and left untouched.
    """
    from django.db import transaction
    from django.utils import timezone
    from apps.channels.models import Channel, ChannelGroup, ChannelStream, Stream
    from apps.epg.models import EPGData, EPGSource
    from apps.m3u.models import M3UAccount

    account = M3UAccount.objects.get(name=ACCOUNT_NAME)
    profile, _ = install_stream_profile()
    start_number = _as_int(settings.get("channel_start_number"), 1000)
    limit = _as_int(settings.get("channel_import_limit"), 25)
    import_mode = str(settings.get("channel_import_mode") or "test_batch").strip().lower()
    if import_mode not in {"test_batch", "epg_only", "all_missing"}:
        import_mode = "test_batch"
    if limit < 0:
        limit = 0

    streams = list(
        Stream.objects.filter(m3u_account=account, is_stale=False)
        .select_related("channel_group")
        .order_by("name", "id")
    )
    existing_auto = {
        cs.stream_id: cs.channel
        for cs in ChannelStream.objects.filter(
            stream__m3u_account=account,
            channel__auto_created=True,
            channel__auto_created_by=account,
        ).select_related("channel", "stream")
    }
    manual_keys = set()
    for ch in Channel.objects.filter(auto_created=False):
        if ch.tvg_id:
            manual_keys.add(("tvg", ch.tvg_id.strip().lower()))
        manual_keys.add(("name", _normalise_channel_name(ch.name)))

    epg_source = EPGSource.objects.filter(custom_properties__has_key=MARKER_KEY).first()
    epg_by_tvg = {}
    if epg_source is not None:
        for epg in EPGData.objects.filter(epg_source=epg_source):
            if epg.tvg_id:
                epg_by_tvg.setdefault(epg.tvg_id.strip().lower(), epg)

    used_numbers = set(Channel.objects.exclude(channel_number__isnull=True).values_list("channel_number", flat=True))
    planned = []
    skipped_existing = 0
    already_linked = 0
    for stream in streams:
        if stream.id in existing_auto:
            already_linked += 1
            continue
        keys = []
        if stream.tvg_id:
            keys.append(("tvg", stream.tvg_id.strip().lower()))
        keys.append(("name", _normalise_channel_name(stream.name)))
        if any(k in manual_keys for k in keys):
            skipped_existing += 1
            continue
        if limit and len(planned) >= limit:
            break
        epg = epg_by_tvg.get((stream.tvg_id or "").strip().lower())
        if import_mode == "epg_only" and epg is None:
            continue
        planned.append({
            "stream_id": stream.id,
            "name": stream.name,
            "tvg_id": stream.tvg_id or "",
            "group": stream.channel_group.name if stream.channel_group else "Kodiboxarr",
            "stream_profile_id": profile.id,
            "epg_data_id": epg.id if epg else None,
            "epg_matched": epg is not None,
            "channel_number": _next_channel_number(used_numbers, start_number),
        })

    created = 0
    linked = 0
    if apply and planned:
        with transaction.atomic():
            for item in planned:
                stream = Stream.objects.select_related("channel_group").get(id=item["stream_id"])
                group = stream.channel_group
                if group is None:
                    group, _ = ChannelGroup.objects.get_or_create(name=item["group"] or "Kodiboxarr")
                epg = EPGData.objects.filter(id=item["epg_data_id"]).first() if item["epg_data_id"] else None
                channel = Channel.objects.create(
                    channel_number=item["channel_number"],
                    name=stream.name,
                    tvg_id=stream.tvg_id,
                    channel_group=group,
                    user_level=0,
                    auto_created=True,
                    auto_created_by=account,
                    epg_data=epg,
                    stream_profile=profile,
                )
                ChannelStream.objects.create(channel=channel, stream=stream, order=0)
                stream.stream_profile = profile
                stream.save(update_fields=["stream_profile", "updated_at"])
                created += 1
                linked += 1

    return {
        "status": "ok",
        "message": f"channel {'apply' if apply else 'plan'}: planned={len(planned)}, created={created}, already_linked={already_linked}, skipped_existing={skipped_existing}",
        "apply": apply,
        "account_id": account.id,
        "stream_count": len(streams),
        "planned_count": len(planned),
        "created_count": created,
        "linked_count": linked,
        "already_linked_count": already_linked,
        "skipped_existing_count": skipped_existing,
        "epg_matched_count": sum(1 for item in planned if item["epg_matched"]),
        "start_number": start_number,
        "limit": limit,
        "import_mode": import_mode,
        "sample": planned[:20],
        "ran_at": timezone.now().isoformat(),
    }


def delete_auto_channels(settings: Dict[str, Any], apply: bool = False) -> Dict[str, Any]:
    """Plan or delete channels owned by Kodiboxarr's marker.

    Manual channels are never touched. This is the quick rollback for staged
    imports during development and safe enough to expose as a plugin action.
    """
    from django.db import transaction
    from django.utils import timezone
    from apps.channels.models import Channel, ChannelStream, Stream
    from apps.m3u.models import M3UAccount

    account = M3UAccount.objects.get(name=ACCOUNT_NAME)
    channels = list(
        Channel.objects.filter(auto_created=True, auto_created_by=account)
        .order_by("channel_number", "id")
    )
    sample = [
        {
            "channel_id": ch.id,
            "channel_number": ch.channel_number,
            "name": ch.name,
            "tvg_id": ch.tvg_id or "",
            "epg_data_id": ch.epg_data_id,
        }
        for ch in channels[:25]
    ]
    deleted_count = 0
    if apply and channels:
        ids = [ch.id for ch in channels]
        with transaction.atomic():
            Stream.objects.filter(m3u_account=account, stream_profile__name=STREAM_PROFILE_NAME).update(stream_profile=None)
            ChannelStream.objects.filter(channel_id__in=ids).delete()
            deleted_count, _ = Channel.objects.filter(id__in=ids).delete()
    return {
        "status": "ok",
        "message": f"auto-channel {'delete' if apply else 'delete-plan'}: owned={len(channels)}, deleted={deleted_count}",
        "apply": apply,
        "owned_count": len(channels),
        "deleted_count": deleted_count,
        "sample": sample,
        "ran_at": timezone.now().isoformat(),
    }


def generate_mapping_report(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a non-mutating report for Kodiboxarr stream/channel/EPG mapping.

    This report is the safety layer before bulk imports: it shows what is
    already linked, what conflicts with manual channels, what can be EPG-mapped,
    and which tvg-id values are ambiguous.
    """
    from collections import Counter, defaultdict
    from django.utils import timezone
    from apps.channels.models import Channel, ChannelStream, Stream
    from apps.epg.models import EPGData, EPGSource
    from apps.m3u.models import M3UAccount

    account = M3UAccount.objects.get(name=ACCOUNT_NAME)
    streams = list(
        Stream.objects.filter(m3u_account=account, is_stale=False)
        .select_related("channel_group")
        .order_by("name", "id")
    )
    auto_channels = list(
        Channel.objects.filter(auto_created=True, auto_created_by=account)
        .select_related("channel_group", "epg_data", "stream_profile")
        .order_by("channel_number", "id")
    )
    manual_channels = list(
        Channel.objects.filter(auto_created=False).select_related("channel_group")
    )

    epg_source = EPGSource.objects.filter(custom_properties__has_key=MARKER_KEY).first()
    epg_data = list(EPGData.objects.filter(epg_source=epg_source)) if epg_source else []
    epg_tvg = {e.tvg_id.strip().lower(): e for e in epg_data if e.tvg_id}

    tvg_counter = Counter((s.tvg_id or "").strip().lower() for s in streams if s.tvg_id)
    duplicate_tvg = {
        tvg: [s.name for s in streams if (s.tvg_id or "").strip().lower() == tvg][:10]
        for tvg, count in tvg_counter.items()
        if count > 1
    }

    manual_by_exact_tvg = {c.tvg_id.strip().lower(): c for c in manual_channels if c.tvg_id}
    manual_by_norm_name = defaultdict(list)
    for c in manual_channels:
        manual_by_norm_name[_normalise_channel_name(c.name)].append(c)

    manual_conflicts = []
    for stream in streams:
        hits = []
        tvg = (stream.tvg_id or "").strip().lower()
        if tvg and tvg in manual_by_exact_tvg:
            ch = manual_by_exact_tvg[tvg]
            hits.append({"reason": "same_tvg_id", "channel_id": ch.id, "channel_number": ch.channel_number, "channel_name": ch.name, "channel_tvg_id": ch.tvg_id or ""})
        for ch in manual_by_norm_name.get(_normalise_channel_name(stream.name), []):
            hits.append({"reason": "same_normalised_name", "channel_id": ch.id, "channel_number": ch.channel_number, "channel_name": ch.name, "channel_tvg_id": ch.tvg_id or ""})
        if hits:
            manual_conflicts.append({"stream_id": stream.id, "stream_name": stream.name, "stream_tvg_id": stream.tvg_id or "", "matches": hits[:5]})

    linked_stream_ids = set(
        ChannelStream.objects.filter(channel__auto_created=True, channel__auto_created_by=account, stream__m3u_account=account)
        .values_list("stream_id", flat=True)
    )
    pending_streams = [s for s in streams if s.id not in linked_stream_ids]
    pending_epg_matches = [s for s in pending_streams if s.tvg_id and s.tvg_id.strip().lower() in epg_tvg]

    report = {
        "status": "ok",
        "message": f"mapping report: streams={len(streams)}, auto_channels={len(auto_channels)}, pending={len(pending_streams)}, epg_matches={sum(1 for s in streams if s.tvg_id and s.tvg_id.strip().lower() in epg_tvg)}",
        "account_id": account.id,
        "stream_count": len(streams),
        "stream_with_tvg_id_count": sum(1 for s in streams if s.tvg_id),
        "unique_stream_tvg_id_count": len(tvg_counter),
        "duplicate_tvg_id_count": len(duplicate_tvg),
        "duplicate_tvg_id_sample": dict(list(duplicate_tvg.items())[:20]),
        "manual_channel_count": len(manual_channels),
        "manual_conflict_count": len(manual_conflicts),
        "manual_conflict_sample": manual_conflicts[:25],
        "auto_channel_count": len(auto_channels),
        "auto_channel_with_stream_count": ChannelStream.objects.filter(channel__in=auto_channels, stream__m3u_account=account).count() if auto_channels else 0,
        "auto_channel_with_epg_count": sum(1 for c in auto_channels if c.epg_data_id),
        "pending_stream_count": len(pending_streams),
        "pending_epg_match_count": len(pending_epg_matches),
        "epg_source_id": getattr(epg_source, "id", None),
        "epg_data_count": len(epg_data),
        "stream_epg_tvg_match_count": sum(1 for s in streams if s.tvg_id and s.tvg_id.strip().lower() in epg_tvg),
        "recommended_next_batch_size": min(25, len(pending_streams)),
        "pending_sample": [
            {
                "stream_id": s.id,
                "name": s.name,
                "tvg_id": s.tvg_id or "",
                "group": s.channel_group.name if s.channel_group else "",
                "epg_matched": bool(s.tvg_id and s.tvg_id.strip().lower() in epg_tvg),
            }
            for s in pending_streams[:25]
        ],
        "ran_at": timezone.now().isoformat(),
    }
    reports = DATA_DIR / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    atomic_write_json(reports / "mapping-report.current.json", report)
    return report


def sync_to_dispatcharr(settings: Dict[str, Any], logger: logging.Logger, dry_run: bool = False) -> Dict[str, Any]:
    """Generate Kodiboxarr data and optionally write Dispatcharr models."""
    plan = create_plan(settings, logger)
    if dry_run:
        return {"status": "ok", "message": _summary(plan, prefix="dry-run"), **_public_plan(plan)}
    if not plan["diff"].get("safe"):
        return {"status": "error", "message": "safety gate blocked sync", **_public_plan(plan)}

    m3u_path = write_m3u(plan["generated_m3u"])
    account = upsert_account(m3u_path, plan["snapshot"], int(settings.get("refresh_hours") or 0))
    epg_source = upsert_epg_source(plan["snapshot"])
    request_reparse(account.id)
    if epg_source is not None:
        request_epg_refresh(epg_source.id)
    profile, profile_created, stream_count, profile_assigned_count = assign_stream_profile_to_account_streams(account)
    _, _, linked_channel_count, channel_profile_assigned_count, channel_profiled_count = assign_stream_profile_to_linked_channels(account)
    atomic_write_json(DATA_DIR / "state/snapshot.json", plan["snapshot"])
    result = _public_plan(plan)
    result.update(
        {
            "status": "ok",
            "message": _summary(plan, prefix="sync") + f"; account_id={account.id}; profile_created={profile_created}; streams_profile_assigned={profile_assigned_count}/{stream_count}; channels_profile_assigned={channel_profile_assigned_count}/{linked_channel_count}",
            "m3u_path": str(m3u_path),
            "account_id": account.id,
            "stream_profile_id": profile.id,
            "stream_count": stream_count,
            "profile_assigned_count": profile_assigned_count,
            "linked_channel_count": linked_channel_count,
            "channel_profile_assigned_count": channel_profile_assigned_count,
            "channel_profiled_count": channel_profiled_count,
            "epg_source_id": getattr(epg_source, "id", None),
        }
    )
    return result


def _summary(plan: Dict[str, Any], prefix: str) -> str:
    snap = plan["snapshot"]
    diff = plan["diff"]
    return f"{prefix}: {snap['channel_count']} channels, EPG={bool((snap.get('epg') or {}).get('url'))}, safe={diff.get('safe')}"


def _public_plan(plan: Dict[str, Any]) -> Dict[str, Any]:
    return {"snapshot": plan["snapshot"], "diff": plan["diff"]}


def _python_executable() -> str:
    import shutil
    import sys

    candidate = sys.executable or ""
    if os.path.basename(candidate).startswith("python"):
        return candidate
    directory = os.path.dirname(candidate)
    for name in ("python3", "python"):
        sibling = os.path.join(directory, name)
        if directory and os.path.exists(sibling):
            return sibling
    return shutil.which("python3") or shutil.which("python") or "python3"
