# Kodiboxarr Roadmap

Kodiboxarr imports and updates streams from Kodibox builds for Dispatcharr. It
must not create Channels automatically; users own Channel creation, EPG mapping,
and which ordered streams are linked to each Channel.

## Principles

- Import streams; never silently create or remap Dispatcharr Channels.
- Keep each provider identifiable and its credentials/secrets out of logs.
- Use Dispatcharr's native ordered ChannelStream failover instead of inventing a
  competing channel-level retry system.
- Make discovery and proposed changes inspectable before writes; destructive or
  bulk actions require explicit user action.
- Prefer small fixture-backed tests and verified plugin ZIPs over live-provider
  assumptions.

## Milestones

Status: **Next** — planned; **In progress** — implementation underway;
**Done** — implemented and verified.

### 1. Provider inventory and Vavoo catalog import — In progress

Tracking: [#7](https://github.com/mildman1848/kodiboxarr/issues/7)

- [x] Verify the shipped cache envelope and implement a URL-free preview for
  provider/group candidate counts and duplicates.
- [x] Add bounded, explicit opt-in M3U import (group-filtered, max 100) with
  stable identities; stream sync still does not create Dispatcharr Channels.
- [x] Resolve catalog pseudo-URLs from exact group/name matches in the verified
  KodiboxTV cache; reject non-HTTPS or non-vavoo.to source URLs.
- [x] Verify stable rendering, group filtering, exact resolver matching, and
  fail-closed handling with synthetic fixtures (15 tests pass; Ruff CI rules pass).
- [ ] Verify on the target Dispatcharr runtime and test actual playback before
  closing the milestone; no live cache/API or production instance was touched.

### 2. StalkerTV via Distalker — In progress

Tracking: [#8](https://github.com/mildman1848/kodiboxarr/issues/8)

- [x] Document [Distalker](https://github.com/PiloUnk/distalker) as the external
  Stalker/MAG portal plugin (separate install, releases, license); Kodiboxarr
  does not implement or vendor a second portal client.
- [x] Describe that Distalker's own M3U streams are linked by the user to an
  existing Channel, and document its credential storage and Channel-level
  stream-profile/fallback behavior per its README.
- [ ] Runtime validation of Kodiboxarr + Distalker streams on one Channel
  (profile assignment, playback, failover) — not yet verified.

### 3. Multi-source Channels and native failover — Next

Tracking: [#9](https://github.com/mildman1848/kodiboxarr/issues/9)

- Let a user link multiple ordered provider streams to one existing Dispatcharr
  Channel (for example, one RTL Channel with KodiboxTV, VavooTV, and StalkerTV
  alternatives).
- Never create duplicate Channels or alter EPG mappings during stream import.
- Resolve a selected candidate using its provider identity and the Channel's
  configured stream profile; Dispatcharr's live proxy owns ordered failover.
- Preserve stable stream identity across refreshes and avoid duplicate links.
- Test primary failure, alternate success, all-candidates-fail, and refresh
  idempotency against supported Dispatcharr behavior.

### 4. Resolver consolidation and hardening — In progress

Tracking: [#10](https://github.com/mildman1848/kodiboxarr/issues/10)

- [x] Share candidate resolution and TCP health checks between playback and
  resolve-only paths; failure diagnostics expose only the resolved edge host.
- [x] Consolidate overlapping Vavoo candidate resolution/probing paths behind
  the shared `resolve_healthy_vavoo_candidate` contract; both resolve-only and
  playback now enforce the same maximum of eight candidate attempts.
- [x] Reject malformed resolver responses and enforce absolute HTTPS URLs with
  a hostname; keep error diagnostics free of incoming URLs and signed paths.
- [x] Test shared resolution, malformed/non-HTTPS responses, HTTP 403/5xx,
  timeouts, empty/exhausted candidates, bounded attempts, and sanitized
  diagnostics with synthetic fixtures.
- [x] Keep Requests TLS verification at its secure default; no global
  `verify=False` or TLS exception exists.
- [ ] Verify on live Dispatcharr and provider endpoints before making runtime or
  playback claims; no live install/playback validation performed.

### 5. Initial release and operational verification — Done (v0.1.0)

- Stable plugin ZIP is built from the release tag and published with `SHA256SUMS`.
- Unit tests, CI lint, plugin ZIP build, and GitHub Actions pass for the release commit.
- Production installation/playback validation remains a separate explicit operation.
