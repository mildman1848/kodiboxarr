# Kodiboxarr

Kodiboxarr is a Dispatcharr plugin that tracks Kodibox builds, imports playlist/EPG metadata, and creates runtime-resolved stream placeholders for Vavoo sources. It does not create Dispatcharr Channels during stream sync; user-managed channel creation remains the default workflow.

## Project links and attribution

- **Original Kodibox project:** [kodibox32/kodibox](https://github.com/kodibox32/kodibox) — this plugin reads its build manifest and build artifacts; it is not affiliated with or endorsed by that project.
- **Dispatcharr:** [Dispatcharr/dispatcharr](https://github.com/Dispatcharr/Dispatcharr) — host application and plugin integration.
- **Vavoo/MediaHubMX:** external service endpoints are used by the resolver. This project is independent and is not affiliated with or endorsed by those services.
- **EPGForgearr:** [mildman1848/epgforgearr](https://github.com/mildman1848/epgforgearr) — separate supplemental XMLTV plugin.
- **Stalker / MAG portals:** [PiloUnk/distalker](https://github.com/PiloUnk/distalker) is a separate Dispatcharr plugin for Stalker portals. Install and configure it separately; Kodiboxarr does not duplicate or vendor its portal client. See [Stalker / MAG portals via Distalker](#stalker--mag-portals-via-distalker-optional-separate-plugin) for setup boundaries and its credential-handling notes.

This repository contains the Kodiboxarr plugin implementation maintained by Mildman1848. It is not a mirror or redistribution of the Kodibox project. Kodibox assets and source archives remain subject to their respective owners' terms.

## Install

1. Download the ZIP attached to a [Kodiboxarr GitHub release](https://github.com/mildman1848/kodiboxarr/releases).
2. Install it through Dispatcharr's plugin manager or the documented plugin-directory workflow for your Dispatcharr version.
3. Configure the Kodibox build manifest and groups, then use **Check build** and **Dry-run sync** before applying a sync.
4. Link imported streams to Channels in Dispatcharr. Stream imports and Channel creation are separate operations.

The plugin catalog is available at:

```text
https://raw.githubusercontent.com/mildman1848/dispatcharr-plugins/main/catalog.json
```

## Stalker / MAG portals via Distalker (optional, separate plugin)

[Distalker](https://github.com/PiloUnk/distalker) is a **separate Dispatcharr plugin** with its own [releases](https://github.com/PiloUnk/distalker/releases) and its own license (AGPL-3.0-only, see its repository's `LICENSE`/`NOTICE`). Kodiboxarr does not bundle, vendor, call, or reimplement it; there is no Stalker code or portal setting in this repository.

- **Install and configure it separately**, following Distalker's own README. As a separate step from any Kodiboxarr sync, Distalker documents that you should restart Dispatcharr after importing or updating it, because workers can hold different plugin code. Plan that restart yourself; nothing in Kodiboxarr performs or requires it.
- **Its streams are its own.** Distalker writes its own M3U-backed account and streams for each portal. Kodiboxarr neither creates nor manages them.
- **You link them to a Channel yourself.** Attach a Distalker stream to an existing Dispatcharr Channel the same way you attach Kodiboxarr streams. Neither plugin creates Channels for this.

### Security notes (from Distalker's documentation)

- Portal credentials exist **unencrypted** in Distalker's files on disk (`/data/distalker/portals.txt` and `/data/distalker/state/*.json`, mode `0600`), plus Redis. Anyone with filesystem access, and any backup of `/data`, can read them. Treat backups accordingly.
- Dispatcharr's plugin settings view shows them redacted, but that does not protect the files.
- No portal credentials or signed URLs belong in this repository, issues, or logs.

### Stream-profile behavior (Channel level)

Dispatcharr picks the stream profile from the **Channel**, not from the individual stream. Distalker assigns its custom `Distalker` profile to a Channel that carries one of its portal streams. Consequently:

- If that Channel also has non-portal streams (for example Kodiboxarr streams), Distalker routes them through its configurable **fallback stream profile** (default `ffmpeg`), which means an ffmpeg remux instead of Dispatcharr's direct relay.
- **Do not set `Distalker` as the global Default Stream Profile**; that would affect every channel.

Kodiboxarr makes no claim of generic Dispatcharr ordered failover or of compatibility beyond what Distalker documents. Mixing Kodiboxarr and Distalker streams on one Channel (and failover between them) has **not been validated at runtime** here; check Distalker's README for its current guidance before relying on it.

## Multiple provider streams on one Channel (manual workflow)

To offer alternatives for one station (for example KodiboxTV, VavooTV, and a Distalker stream), build the Channel yourself in Dispatcharr:

1. Create or pick the Channel in Dispatcharr.
2. In the Dispatcharr UI, add each provider's stream to that Channel and drag them into the order you want tried. That order is the failover order; Dispatcharr's live proxy owns it.
3. Run `assign_profile` (optional, see below).

Kodiboxarr's boundaries:

- It imports **only its own streams**. It never creates Channels, and it never creates, removes, or reorders `ChannelStream` links or touches EPG mappings on a Channel you built.
- Linking and ordering happen only in the Dispatcharr UI.
- `assign_profile` sets the Kodiboxarr stream profile on the Kodiboxarr streams, and **fills the stream profile only on linked Channels that have none**. A Channel with a non-empty profile keeps it unless an overwrite is explicitly requested in code; the plugin action does not request it. Links and their order are not changed.
- Because the profile is per Channel, a mixed Channel runs every stream through that one profile. Runtime playback and failover across mixed providers are **not verified**.

## Development

```bash
python3 -m pip install pytest requests
python3 -m pytest -q
python3 scripts/build_plugin_zip.py
```

The ZIP builder includes only runtime plugin files. It excludes tests, Git metadata, Python bytecode, local state, signatures, and downloaded Kodibox build data.

### Vavoo catalog preview

The KodiboxTV build stores its Vavoo cache as zlib-compressed JSON at `userdata/addon_data/plugin.video.kodiboxtv/cache/vav_channels`. The verified envelope is `value.channels`; each channel record has `name`, `group`, and a playback `url`. Kodiboxarr discards that URL from the M3U, derives a stable opaque candidate identity from normalized name + group, and preserves regional variants by group. Run **Dry-run sync** to prepare the current build cache, then use **Vavoo catalog preview**. Import is off by default; to opt in, select exact group names from the preview and set an import limit (1–100). This adds only M3U streams, never Dispatcharr Channels. The resolver uses exact group/name matches in the same cache and accepts only HTTPS URLs on `vavoo.to`; existing Kodi/XStream resolution remains separate. Unit tests use synthetic cache fixtures only; live Dispatcharr playback has not been verified.

## Security and privacy

- Do not commit downloaded build archives, extracted provider caches, signed stream URLs, MediaHubMX signatures, or Dispatcharr data.
- Treat resolver output and playback URLs as sensitive, short-lived credentials. Do not paste complete URLs into issues or logs.
- Resolver credentials/signatures are requested at runtime and cached only in Dispatcharr's data directory.
- Report vulnerabilities privately through GitHub Security Advisories.

## License

AGPL-3.0-only. See [LICENSE](LICENSE).
