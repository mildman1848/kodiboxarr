# Changelog

## 0.1.4 — 2026-11-19

- Cap Vavoo candidate resolution and playback failover at eight attempts per
  request; empty candidate sets now return a clear cache/mapping diagnostic.
- Classify HTTP status, timeout, TLS, network, malformed-response, resolver, and
  stream failures without logging exception messages or signed source URLs.
- Add synthetic regression coverage for HTTP 403/503, timeouts, empty/exhausted
  candidate sets, attempt bounds, and signed URL secrecy. HTTP 403 is reported as
  potentially expired or forbidden; expiry cannot be distinguished provider-side.
- TLS certificate verification remains enabled by Requests defaults. No live
  Dispatcharr installation or playback was performed.

## 0.1.3 — 2026-11-19

- Consolidated Vavoo candidate resolution and TCP health checks across playback
  and resolve-only paths; failed-probe diagnostics expose only the edge host.
- Reject malformed resolver responses and non-HTTPS or hostless URLs without
  including the incoming source URL in errors. TLS verification remains enabled.
- Added regression coverage for shared resolution, malformed responses, HTTPS
  validation, and sanitized diagnostics. Resolver roadmap item #10 remains open:
  HTTP errors/timeouts, expired URLs and full candidate exhaustion need more
  coverage; live Dispatcharr playback was not verified.
- Documented Distalker as a separate Stalker/MAG plugin, including its own
  install/update guidance, M3U streams, manual Channel linking, credential
  storage risks, and Channel-level stream-profile/fallback behavior.
- Runtime validation of mixed Kodiboxarr/Distalker Channels and failover remains
  outstanding; no compatibility claim is made.

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
