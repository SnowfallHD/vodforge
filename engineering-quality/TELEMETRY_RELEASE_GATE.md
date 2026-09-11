# Telemetry release gate

A release must prove telemetry with real UI actions in final signed artifacts on
**macOS and Windows**, against **vodforge_preview**. Telemetry-off E2E alone is
insufficient. Do not publish when either platform's evidence is absent, skipped,
failed, stale, or from a rebuilt artifact.

## Isolation and final artifacts

Use the normal final production-policy artifact. Do not modify its policy marker,
re-sign it, or substitute a preview rebuild after testing. The explicit combination
`VODFORGE_QUALITY_E2E=1`, `VODFORGE_QA_PREVIEW_TELEMETRY=1`, a valid private
`VODFORGE_QA_ACCESS_KEY`, and an absolute isolated `VODFORGE_QA_PROFILE` routes
telemetry exclusively to the fixed preview host. Production telemetry remains
forbidden. Disabled artifacts cannot be enabled by these flags. The unconditional
`VODFORGE_DISABLE_TELEMETRY=1` switch is retained for the negative journey.

The maintained Mac launcher supports `packaged-e2e --profile telemetry --telemetry preview`; it sets
an isolated profile and removes the off switch only from its own child environment.
Supply the QA key privately in the parent environment, never in receipts, commands,
source, or the artifact. Windows journeys must use the same explicit environment
and isolated state, retaining native PID/executable/signature and archive receipts.
Do not use a user's normal profile. The existing Windows consent-only driver is
not an all-event release journey and cannot substitute for this gate.

Verify the preview config binds Worker `vodforge-preview`, no production routes,
and D1 `924640fb-3be3-47ca-992c-1c7745bd8469`. Apply the same site migrations to
preview and deploy its current handlers through the site's guarded preview script.
Record the site commit/deployment version alongside the report. Do not copy
production users or change production data to create test fixtures.

## Required observed journey

Use the recorder's `telemetry` profile, which requires native screenshots for all
producer actions and refusal/disabled observations. Follow its ordered event list:
complete the media actions during the first session, reopen, then capture the
same-version and completed-event readbacks before the negative checks. The
checkpoints below describe the assertions, not an alternate recorder order.

Retain the UI action ledger, screenshots, exact candidate archive/executable hashes,
process launch identities, source commit, platform, and raw scoped D1 checkpoints.
A helper directly posting events is a transport test, not packaged journey proof.

1. Fresh isolated profile: decline or leave permission unknown; verify no optional
   telemetry rows and capture `unknown.json`. Grant permission through the UI. Observe one installation and
   credential, first launch and app-open event. Capture `first_launch.json`.
2. Quit normally. Reopen the **same version and same profile** after the timestamp
   second changes. Verify last seen advances; first launch, creation date, identity
   and current version stay fixed; no update event appears. Capture
   `same_version_reopen.json`. Repeated UI callbacks within one session must not
   create extra app-open events.
3. Through actual UI actions, complete MP4, MP3 and Original-audio runs; play each;
   stop an active run; cause a controlled failure and retry it; complete local
   audio + image → MP4. Open Settings and use Cloud interest. Record exact expected
   counts from these actions, including starts and terminal outcomes for each
   attempt. Capture `events_complete.json`. Keep bounded failure facts and exact
   event IDs. Validate the media output independently as part of ordinary E2E.
4. Turn analytics off through Settings, quit/reopen, and exercise actions again.
   Capture `denied.json`; installation observations and event rows must not change.
5. With the same isolated profile, run the explicit telemetry-disabled negative
   journey, including app open and media use. Capture `disabled.json`; D1 must
   remain unchanged. Also retain transport suppression tests for unknown consent.
6. In a separate isolated upgrade profile, capture `update_before.json` on the
   previous version and `update_after.json` after the real upgrade to the candidate.
   Require the same installation, exactly one correct client_update transition,
   current version advancement, and no duplicate transition after another launch.
7. Repeat on Windows. Cover accepted/refused/unknown regional permission, browser
   claim source attribution and refusal, offline retry, exact retry deduplication,
   rate limiting, credential conflict and revocation in the required backend/local
   contracts. Provider delivery is explicitly separate: preview excludes HeyCatch;
   never claim provider certification from preview D1.

## Direct D1 readbacks and enforcement

While each packaged session runs, capture its scoped rows (SELECT only):

```sh
./engineering-quality/run telemetry-snapshot \
  --site ../vodforge-site \
  --session engineering-quality/reports/<journey>/session.json \
  --output engineering-quality/reports/<journey>/snapshots/first_launch.json
```

Repeat for each checkpoint. The session must identify the actual isolated profile
and immutable candidate binding. The command rejects a different database or
production Worker configuration and exports no credentials or contact data.
Use the corresponding baseline session for `update_before.json`.

`expected-counts.json` is the explicit event-name/count mapping from the UI ledger;
all current product events must be present with positive counts. Do not copy counts
from D1 to make a failed journey pass. Original audio is explicitly labeled `original` in schema v2; legacy schema-v1
acceptance is covered independently.

```sh
./engineering-quality/run telemetry-verify \
  --candidate engineering-quality/candidates/<id>/candidate-artifact.json \
  --e2e-result engineering-quality/reports/<journey>/e2e-result.json \
  --snapshots engineering-quality/reports/<journey>/snapshots \
  --expected-counts engineering-quality/reports/<journey>/expected-counts.json \
  --platform macos \
  --output engineering-quality/reports/<journey>/telemetry-result.json
```

Pass both platform results as repeated `--telemetry-result` arguments to
`release-receipt`. It recomputes the metric checks from the readbacks; a supplied
`status: passed` cannot bypass missing checkpoints, wrong source/artifact, stale
last seen, missing or duplicate events, missing update evidence, or privacy writes.
Final publication still requires the ordinary signature, updater, media, UI and
artifact-integrity checks. A review-only draft upload is not publication.

## Schema v2 feature coverage

The canonical desktop vocabulary is `yt_downloader/telemetry_features.py`, with
product event names owned by `product_telemetry.py`. Backend normalization must
match that vocabulary; widening an enum requires a contract test, a migration if
needed, a real producer test, and an updated native preview journey. Never add
arbitrary property bags, search text, URLs, media titles, notes, category names,
paths, raw accent colors, or hardware identifiers.

For current candidates, require schema v2 and explicit `original` format. The
older schema-v1 contract stays accepted for released clients and pending outboxes;
its unlabeled formats must not be backfilled by guessing.

The release verifier now requires every feature/action pair, all six MP4 presets,
CPU exports and Windows NVIDIA exports, and the added queue, skip, local-conversion
and per-media export events. Native screenshots must cover the corresponding
`*_observed` actions in the telemetry recorder. Exercise actual failed and cancelled
local conversions, partial playlists, queue removal, a skipped item, retries,
Library search/filter/selection/removal, notes/tags/categories, playback completion
and failure, seeking/chapters/heatmaps/previews, missing-file recovery, What’s New
Try it, Technical view, appearance changes, and update/Repair outcomes. UI action
and expected counts must be recorded before reading D1, never inferred from rows.

Compare `attempt_id` across start/outcome and `retry_of` to the previous attempt.
They are installation-scoped opaque UUIDs, independent of content and local paths.
One attempt may produce multiple `media_exported` events in a playlist. Each must
represent validated, committed media. Check actual encoder/rate-control and
bucketed resolution, duration, processing time, queue wait and size; configuration
intent cannot substitute for output facts. Timing unavailable after a restart is
omitted rather than fabricated. Original audio reports stream copy.

Engagement feature/actions are recorded once per consent-enabled process session,
not per keystroke or poll. Update actions are individual observations. Relaunch
confirmation requires the helper receipt and the currently executing file's hash;
a download or handoff is not update completion. Keep detached-helper repair/failure
and ordinary app-start cases in both platform updater regressions.

All new events and properties must also pass unknown/denied/off suppression,
allow-list rejection, outbox restart, exact delivery retry/conflict and credential
isolation checks. A direct serializer-to-preview-D1 test establishes transport and
storage only; it does not replace native source callbacks or final signed-artifact
UI evidence. Preview excludes the external provider; provider serialization and
consent regressions remain separate.
