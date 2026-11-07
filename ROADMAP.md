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

### 2. StalkerTV via Distalker — Next

Tracking: [#8](https://github.com/mildman1848/kodiboxarr/issues/8)

- Document Distalker as the external Stalker/MAG portal plugin; Kodiboxarr does
  not implement or vendor a second portal client.
- Describe how Distalker-generated M3U streams can coexist with Kodiboxarr and
  be linked by the user to an existing Channel in Dispatcharr.
- Verify/document stream-profile assignment and current compatibility boundaries
  for using Distalker streams as ordered alternatives on a Channel.
- Link to Distalker's own releases, license, credential handling, and update
  notes; keep Distalker code and portal credentials outside this repository.

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

### 4. Resolver consolidation and hardening — Next

Tracking: [#10](https://github.com/mildman1848/kodiboxarr/issues/10)

- Consolidate overlapping Vavoo candidate resolution/probing paths behind one
  provider-aware resolver contract.
- Bound retries and candidate attempts; expose actionable sanitized diagnostics.
- Verify TLS certificates by default; any narrowly scoped exception must be
  explicit, documented, and tested (never a global `verify=False`).
- Add regression tests for HTTP errors, timeouts, malformed responses, expired
  URLs, and failover exhaustion.

### 5. Initial release and operational verification — Done (v0.1.0)

- Stable plugin ZIP is built from the release tag and published with `SHA256SUMS`.
- Unit tests, CI lint, plugin ZIP build, and GitHub Actions pass for the release commit.
- Production installation/playback validation remains a separate explicit operation.
