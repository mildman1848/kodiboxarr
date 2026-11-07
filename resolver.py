#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import re
import select
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from kodiboxarr.vavoo_cache import KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH, read_cache

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime in Dispatcharr container
    requests = None

PSEUDO_HOST = "kodiboxarr.invalid"
DATA_DIR = Path(os.environ.get("KODIBOXARR_DATA_DIR", "/data/kodiboxarr"))
CACHE_RELATIVE_PATH = "userdata/addon_data/plugin.video.xstream/vavoo/channels_group_Germany.json"
CACHE_PATH = Path(os.environ.get("KODIBOXARR_VAVOO_CACHE", DATA_DIR / "extracted/buildzip" / CACHE_RELATIVE_PATH))
KODIBOXTV_CACHE_PATH = Path(os.environ.get(
    "KODIBOXARR_KODIBOXTV_VAVOO_CACHE",
    DATA_DIR / "extracted/buildzip" / KODIBOXTV_VAVOO_CACHE_RELATIVE_PATH,
))
SIGNATURE_CACHE = Path(os.environ.get("KODIBOXARR_SIGNATURE_CACHE", DATA_DIR / "state/mediahubmx-signature.json"))
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
MEDIAHUB_UA = "MediaHubMX/2"
CLIENT_VERSION = "3.1.0"
FFMPEG_READ_CHUNK = int(os.environ.get("KODIBOXARR_FFMPEG_READ_CHUNK", str(16 * 1024)))
FFMPEG_STALL_SECONDS = float(os.environ.get("KODIBOXARR_FFMPEG_STALL_SECONDS", "10.0"))
FFMPEG_REALTIME = os.environ.get("KODIBOXARR_FFMPEG_REALTIME", "1").lower() not in {"0", "false", "no", "off"}


def log(message: str) -> None:
    print(f"[kodiboxarr] {message}", file=sys.stderr, flush=True)


def safe_url_host(url: str) -> str:
    """Return only a URL host for diagnostics; never log signed paths or queries."""
    return urlparse(url).hostname or "unknown-host"


def is_ours(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == PSEUDO_HOST


def decode_payload(url: str) -> dict:
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("Kodiboxarr pseudo-url must be /<provider>/<payload>")
    provider, encoded = parts[0], parts[1]
    padded = encoded + ("=" * (-len(encoded) % 4))
    payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    if payload.get("provider") and payload["provider"] != provider:
        raise ValueError(f"provider mismatch: path={provider}, payload={payload['provider']}")
    payload.setdefault("provider", provider)
    return payload


def normalise_name(value: str) -> str:
    value = (value or "").upper()
    value = value.replace("&AMP;", "&")
    value = value.replace("+", " PLUS ")
    value = re.sub(r"\bHD\+?\b", "", value)
    value = re.sub(r"\b(UHD|FHD|HEVC|RAW|SD|4K)\b", "", value)
    value = re.sub(r"\bBACKUP(\s*\d+)?\b", "", value)
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


# Modifier words that distinguish quality/event variants of the same channel,
# not different channels. Stripped in the last-resort sloppy matching tier.
SLOPPY_MODIFIERS = {
    "HD", "FHD", "UHD", "4K", "HEVC", "RAW", "SD", "LQ", "HQ",
    "BACKUP", "EVENT", "EVENTS", "MATCH", "TIME", "LIVE", "DURING",
    "ONLY", "PLUS", "BAR", "LOCAL", "TOP", "VIDEO", "AUDIO",
}


def sloppy_key(value: str) -> str:
    """Aggressive normalisation for last-resort matching.

    Folds umlauts (both unicode and ASCII forms), removes quality/event
    modifier words, '+1' timeshift suffixes and every non-alphanumeric.
    'DAZN EVENT 16 HD' and 'DAZN 16' both become 'DAZN16'.
    """
    value = (value or "").upper()
    for src, dst in (("Ü", "UE"), ("Ä", "AE"), ("Ö", "OE"), ("ß", "SS")):
        value = value.replace(src, dst)
    value = re.sub(r"\+1\b", " ", value)  # timeshift suffix
    value = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", value)
    tokens = [t for t in re.split(r"[^A-Z0-9]+", value) if t and t not in SLOPPY_MODIFIERS]
    return "".join(tokens)


def load_vavoo_cache(path: Path = CACHE_PATH) -> dict[str, list[str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    value = raw.get("value") if isinstance(raw, dict) else raw
    if not isinstance(value, dict):
        raise ValueError(f"unexpected Vavoo cache format in {path}")
    out: dict[str, list[str]] = {}
    for name, urls in value.items():
        if not isinstance(name, str) or not isinstance(urls, list):
            continue
        valid = [u for u in urls if isinstance(u, str) and "vavoo" in u]
        if valid:
            out[name] = valid
    return out


def candidate_names(payload: dict) -> list[str]:
    names = []
    for key in ("kodibox_name", "name", "identity"):
        value = (payload.get(key) or "").strip()
        if value and value not in names:
            names.append(value)
    return names


def _catalog_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def load_kodiboxtv_vavoo_candidates(payload: dict, path: Path | None = None) -> list[str]:
    """Find exact group/name matches in KodiboxTV's compressed Vavoo cache."""
    name = payload.get("name")
    group = payload.get("group")
    if not isinstance(name, str) or not name.strip() or not isinstance(group, str):
        raise ValueError("KodiboxTV catalog payload is missing channel name or group")
    cache = read_cache(path or KODIBOXTV_CACHE_PATH)
    value = cache.get("value")
    channels = value.get("channels") if isinstance(value, dict) else None
    if not isinstance(channels, list):
        raise ValueError("KodiboxTV Vavoo cache has no channels list")

    matches: list[str] = []
    wanted = (_catalog_key(group), _catalog_key(name))
    for item in channels:
        if not isinstance(item, dict):
            continue
        if (_catalog_key(str(item.get("group", ""))), _catalog_key(str(item.get("name", "")))) != wanted:
            continue
        url = item.get("url")
        if not isinstance(url, str):
            continue
        parsed = urlparse(url)
        try:
            has_port = parsed.port is not None
        except ValueError:
            continue
        if parsed.scheme != "https" or parsed.hostname != "vavoo.to" or parsed.username or parsed.password or has_port:
            continue
        if url not in matches:
            matches.append(url)
    if not matches:
        raise KeyError("no exact KodiboxTV Vavoo cache entry for requested group/channel")
    return matches


def _prefer_variant(candidates: list[str], payload: dict) -> list[str]:
    """Try the candidate matching this stream's variant first; the rest stay as fallbacks."""
    variant = payload.get("variant")
    if isinstance(variant, int) and 0 < variant < len(candidates):
        return [candidates[variant], *candidates[:variant], *candidates[variant + 1 :]]
    return candidates


def choose_vavoo_url(payload: dict, cache: dict[str, list[str]] | None = None) -> str:
    candidates = list_vavoo_candidates(payload, cache)
    return candidates[0]


def list_vavoo_candidates(payload: dict, cache: dict[str, list[str]] | None = None) -> list[str]:
    """Return all known Vavoo source URLs for the channel, primary first.

    Order: exact-name hits first (they are most likely the intended quality
    variant), then normalised matches. Backup/HD+/HEVC variants are appended
    last as failover sources.
    """
    if payload.get("source") == "kodiboxtv_catalog":
        return _prefer_variant(load_kodiboxtv_vavoo_candidates(payload), payload)
    cache = cache or load_vavoo_cache()
    exact: list[str] = []
    fallback: list[str] = []
    for name in candidate_names(payload):
        variants = [name, name.upper(), name.replace(" TV", ".TV"), name.replace("-", ".")]
        for variant in variants:
            if variant in cache and cache[variant]:
                bucket = exact if variant == name or variant == name.upper() else fallback
                for url in cache[variant]:
                    if url not in bucket:
                        bucket.append(url)

    norm_index: dict[str, list[str]] = {}
    for key in cache:
        norm_index.setdefault(normalise_name(key), []).append(key)
    for name in candidate_names(payload):
        norm = normalise_name(name)
        for key in norm_index.get(norm, []):
            for url in cache[key]:
                if url not in exact and url not in fallback:
                    fallback.append(url)

    # Tier 3 (last resort): sloppy matching folds umlauts and quality/event
    # modifiers, e.g. 'DAZN 16' <-> 'DAZN EVENT 16 HD', 'MUENCHEN TV' <-> 'MÜNCHEN TV'.
    sloppy_index: dict[str, list[str]] = {}
    for key in cache:
        sloppy_index.setdefault(sloppy_key(key), []).append(key)
    for name in candidate_names(payload):
        key = sloppy_key(name)
        for cached in sloppy_index.get(key, []):
            for url in cache[cached]:
                if url not in exact and url not in fallback:
                    fallback.append(url)

    ordered = exact + fallback
    if not ordered:
        raise KeyError(f"no Vavoo cache entry for {candidate_names(payload)}")
    return _prefer_variant(ordered, payload)


def _decode_auth_signature(signature: str) -> dict | None:
    if not signature:
        return None
    try:
        encoded = signature.encode("ascii")
        encoded += b"=" * (-len(encoded) % 4)
        envelope = json.loads(base64.urlsafe_b64decode(encoded).decode("utf-8"))
        payload = envelope.get("data")
        if isinstance(payload, str):
            payload = json.loads(payload)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def signature_valid_until(signature: str) -> int | None:
    payload = _decode_auth_signature(signature)
    if not payload or not isinstance(payload.get("app"), dict) or payload["app"].get("ok") is not True:
        return None
    try:
        valid_until = int(payload.get("validUntil"))
    except (TypeError, ValueError):
        return None
    if valid_until < 100000000000:
        valid_until *= 1000
    if valid_until <= int(time.time() * 1000) + 30_000:
        return None
    return valid_until


def build_signature_payload() -> dict:
    uid = str(uuid.uuid4())
    ts = int(time.time() * 1000)
    return {
        "reason": "app-focus",
        "locale": "en",
        "theme": "dark",
        "metadata": {
            "device": {"type": "desktop", "uniqueId": uid},
            "os": {"name": "win32", "version": "Windows 10 Pro", "abis": ["x64"], "host": "Lenovo"},
            "app": {"platform": "electron"},
            "version": {"package": "net.vypn.app", "binary": CLIENT_VERSION, "js": CLIENT_VERSION},
        },
        "appFocusTime": 0,
        "playerActive": False,
        "playDuration": 0,
        "devMode": False,
        "hasAddon": True,
        "castConnected": False,
        "package": "net.vypn.app",
        "version": CLIENT_VERSION,
        "process": "app",
        "firstAppStart": ts,
        "lastAppStart": ts,
        "ipLocation": None,
        "adblockEnabled": True,
        "proxy": {"supported": ["ss"], "engine": "Mu", "enabled": False, "autoServer": True},
        "iap": {"supported": False},
    }


def get_auth_signature() -> str:
    if requests is None:
        raise RuntimeError("requests is not installed")
    try:
        cached = json.loads(SIGNATURE_CACHE.read_text(encoding="utf-8"))
        sig = cached.get("signature", "")
        valid_until = signature_valid_until(sig)
        if valid_until:
            log(f"using cached MediaHubMX signature, valid for {int((valid_until - time.time() * 1000) / 1000)}s")
            return sig
    except Exception:
        pass

    response = requests.post(
        "https://www.vypn.net/api/app/ping",
        json=build_signature_payload(),
        headers={"accept": "*/*", "user-agent": BROWSER_UA, "Accept-Encoding": "gzip, deflate", "Connection": "close"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    sig = data.get("sig") or data.get("addonSig") or data.get("signature") or data.get("mediahubmxSignature") or data.get("mediahubmx-signature")
    valid_until = signature_valid_until(sig or "")
    if not valid_until:
        raise RuntimeError("MediaHubMX signature response was missing or expired")
    SIGNATURE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SIGNATURE_CACHE.write_text(json.dumps({"signature": sig, "valid_until": valid_until}, sort_keys=True), encoding="utf-8")
    log(f"received MediaHubMX signature, valid for {int((valid_until - time.time() * 1000) / 1000)}s")
    return sig


def resolve_vavoo_link(vavoo_url: str) -> str:
    if requests is None:
        raise RuntimeError("requests is not installed")
    signature = get_auth_signature()
    response = requests.post(
        "https://vavoo.to/mediahubmx-resolve.json",
        json={"language": "de", "region": "AT", "url": vavoo_url, "clientVersion": CLIENT_VERSION},
        headers={"user-agent": MEDIAHUB_UA, "content-type": "application/json; charset=utf-8", "accept-encoding": "gzip", "mediahubmx-signature": signature},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list) or not data or not data[0].get("url"):
        raise RuntimeError(f"unexpected resolve response for {vavoo_url}")
    return data[0]["url"]


def probe_resolved_url(url: str, timeout: float = 5.0) -> bool:
    """Lightweight health check before handing a signed URL to ffmpeg.

    Important: do not HTTP-GET the resolved HLS URL here. Some MediaHubMX/Vavoo
    edges treat the resolved URL as short-lived or single-consumer-ish; reading
    even one chunk can make the following ffmpeg process receive 403 Forbidden.
    TCP connect still catches completely dead edges without consuming the media
    token.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


def resolve_pseudo_url(url: str) -> str:
    payload = decode_payload(url)
    if payload.get("provider") != "vavoo":
        raise ValueError(f"unsupported provider: {payload.get('provider')}")
    candidates = list_vavoo_candidates(payload)
    name = payload.get("name") or payload.get("kodibox_name")
    log(f"matched {name} -> {len(candidates)} candidate(s), primary host {safe_url_host(candidates[0])}")
    last_error: Exception | None = None
    for index, vavoo_url in enumerate(candidates):
        try:
            resolved = resolve_vavoo_link(vavoo_url)
            if probe_resolved_url(resolved):
                if index:
                    log(f"primary source unhealthy; using candidate #{index + 1} for {name}")
                return resolved
            log(f"candidate #{index + 1} resolved but failed probe at host {safe_url_host(resolved)}")
            last_error = RuntimeError("resolved URL probe failed")
        except Exception as exc:  # noqa: BLE001 - try next candidate on any failure
            log(f"candidate #{index + 1} failed for {name}: {type(exc).__name__}")
            last_error = exc
    raise RuntimeError(f"all {len(candidates)} candidates failed for {name}: {type(last_error).__name__ if last_error else 'unknown error'}")


def _ffmpeg_command(url: str, user_agent: str) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-user_agent",
        user_agent or "",
        "-rw_timeout",
        "10000000",
    ]
    if FFMPEG_REALTIME:
        command.append("-re")
    command.extend([
        "-i",
        url,
        "-c",
        "copy",
        "-f",
        "mpegts",
        "pipe:1",
    ])
    return command


def passthrough(url: str, user_agent: str) -> int:
    command = _ffmpeg_command(url, user_agent)
    executable = shutil.which(command[0]) or command[0]
    try:
        os.execv(executable, command)
    except OSError as exc:
        log(f"cannot execute {executable}: {exc}")
        return 1
    return 1


def stream_resolved_url(url: str, user_agent: str) -> tuple[int, int, str]:
    """Run ffmpeg and copy MPEG-TS stdout to our stdout.

    Returns (exit_code, bytes_written, reason). If ffmpeg stalls or exits before
    producing useful data, the caller can try the next resolved mirror. Reads are
    intentionally small and select-driven; a blocking 64 KiB read makes live TV
    feel laggy and hides Vavoo CDN stalls from the resolver.
    """
    executable = shutil.which("ffmpeg") or "ffmpeg"
    command = _ffmpeg_command(url, user_agent)
    command[0] = executable
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=sys.stderr)
    written = 0
    last_data_at = time.monotonic()
    try:
        assert process.stdout is not None
        fd = process.stdout.fileno()
        while True:
            rc = process.poll()
            if rc is not None:
                chunk = os.read(fd, FFMPEG_READ_CHUNK)
                if chunk:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.buffer.flush()
                    written += len(chunk)
                return rc, written, "exited"

            ready, _, _ = select.select([fd], [], [], 0.5)
            if not ready:
                idle = time.monotonic() - last_data_at
                if written == 0 and idle >= FFMPEG_STALL_SECONDS:
                    log(f"ffmpeg produced no data for {idle:.1f}s; terminating candidate")
                    process.terminate()
                    try:
                        rc = process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        rc = process.wait()
                    return rc or 124, written, "stall"
                continue

            chunk = os.read(fd, FFMPEG_READ_CHUNK)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            written += len(chunk)
            last_data_at = time.monotonic()
        return process.wait(), written, "eof"
    except BrokenPipeError:
        try:
            process.terminate()
        except Exception:
            pass
        return 0, written, "client_disconnected"


def passthrough_vavoo_payload(payload: dict, user_agent: str) -> int:
    candidates = list_vavoo_candidates(payload)
    name = payload.get("name") or payload.get("kodibox_name")
    log(f"matched {name} -> {len(candidates)} candidate(s), primary host {safe_url_host(candidates[0])}")
    last_error: Exception | None = None
    for index, vavoo_url in enumerate(candidates):
        try:
            resolved = resolve_vavoo_link(vavoo_url)
            if not probe_resolved_url(resolved):
                log(f"candidate #{index + 1} failed TCP probe: {resolved[:80]}")
                continue
            if index:
                log(f"using candidate #{index + 1} for {name}")
            else:
                log(f"using candidate #1 for {name}")
            rc, written, reason = stream_resolved_url(resolved, user_agent or "libmpv")
            if written > 0 and rc == 0:
                log(f"candidate #{index + 1} produced {written} bytes; ffmpeg exited rc={rc} reason={reason}")
                return rc
            if written > 0:
                log(f"candidate #{index + 1} produced {written} bytes then stopped rc={rc} reason={reason}")
                return rc
            else:
                log(f"candidate #{index + 1} produced no data rc={rc} reason={reason}; trying next mirror")
        except Exception as exc:  # noqa: BLE001 - try next candidate on any failure
            log(f"candidate #{index + 1} failed for {name}: {type(exc).__name__}")
            last_error = exc
    raise RuntimeError(f"all {len(candidates)} candidates failed for {name}: {type(last_error).__name__ if last_error else 'unknown error'}")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        log("usage: resolver.py [--resolve-only] <stream-url> [user-agent]")
        return 2
    resolve_only = argv[1] == "--resolve-only"
    url_index = 2 if resolve_only else 1
    if len(argv) <= url_index:
        log("missing stream-url")
        return 2
    url = argv[url_index]
    user_agent = argv[url_index + 1] if len(argv) > url_index + 1 else ""
    try:
        if not is_ours(url):
            log("not a Kodiboxarr source; passing through to ffmpeg")
            return passthrough(url, user_agent)
        payload = decode_payload(url)
        if payload.get("provider") != "vavoo":
            raise ValueError(f"unsupported provider: {payload.get('provider')}")
        if resolve_only:
            print(resolve_pseudo_url(url))
            return 0
        return passthrough_vavoo_payload(payload, user_agent)
    except Exception as exc:
        log(f"resolve failed: {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
