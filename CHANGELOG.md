# Changelog

## 0.1.1 — 2026-11-06

- Corrected the displayed plugin author to `Mildman1848` only.
- Added a bounded, URL-free preview of the KodiboxTV Vavoo catalogue cache.

## 0.1.0 — 2026-11-06

- Initial stable release of the Kodiboxarr Dispatcharr plugin.
- Added safe build discovery, dry-run sync, stream/EPG metadata synchronization,
  mapping reports, and explicit reversible channel helper actions.
- Added runtime Vavoo candidate resolution and bounded mirror failover.
- Sanitized resolver diagnostics so signed URLs and query tokens are not written
  to Kodiboxarr logs.
- Removed unused `groups` and `fallback_profile` settings and corrected the
  stream-profile action description.
- Stalker/MAG portal integration is provided by the separate
  [Distalker project](https://github.com/PiloUnk/distalker); Kodiboxarr does not
  vendor or reimplement its portal client.
