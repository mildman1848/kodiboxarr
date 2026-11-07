# Changelog

## 0.1.2 — 2026-11-07

- Added an opt-in, off-by-default import of selected KodiboxTV Vavoo catalog
  groups into the generated M3U (settings: `include_vavoo_catalog`,
  `vavoo_catalog_groups`, `vavoo_catalog_import_limit`; at most 100 candidates
  per sync). It adds M3U streams only, never Dispatcharr Channels, and warns
  instead of importing when the cache, groups, or limit are missing.
- Catalog streams carry opaque placeholder URLs; the resolver matches exact
  group/name in the KodiboxTV cache and accepts only HTTPS `vavoo.to` URLs,
  failing closed otherwise.
- Distinct source URLs for the same service are kept apart with a stable variant
  ordinal (resolver tries that variant first); exact duplicate URLs are dropped.
  Source URLs are not stored in placeholders.
- Tests added with synthetic fixtures (18 pass locally). Live Dispatcharr
  playback and the target runtime were not verified.

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
