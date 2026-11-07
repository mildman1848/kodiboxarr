# Kodiboxarr

Kodiboxarr is a Dispatcharr plugin that tracks Kodibox builds, imports playlist/EPG metadata, and creates runtime-resolved stream placeholders for Vavoo sources. It does not create Dispatcharr Channels during stream sync; user-managed channel creation remains the default workflow.

## Project links and attribution

- **Original Kodibox project:** [kodibox32/kodibox](https://github.com/kodibox32/kodibox) — this plugin reads its build manifest and build artifacts; it is not affiliated with or endorsed by that project.
- **Dispatcharr:** [Dispatcharr/dispatcharr](https://github.com/Dispatcharr/Dispatcharr) — host application and plugin integration.
- **Vavoo/MediaHubMX:** external service endpoints are used by the resolver. This project is independent and is not affiliated with or endorsed by those services.
- **EPGForgearr:** [mildman1848/epgforgearr](https://github.com/mildman1848/epgforgearr) — separate supplemental XMLTV plugin.
- **Stalker / MAG portals:** [PiloUnk/distalker](https://github.com/PiloUnk/distalker) is a separate Dispatcharr plugin for Stalker portals. Install and configure it separately; Kodiboxarr does not duplicate or vendor its portal client. Distalker documents that portal credentials are stored in its own state files, so review its security notes before configuring a portal.

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
