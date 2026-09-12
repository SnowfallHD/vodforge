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

### Execution discipline

For macOS, use the maintained native input driver below instead of ad-hoc scripts
under `build/`. It resolves only the attested session PID, checks the exact focused
window, clears inherited shortcut modifiers, and can wait up to five seconds for
an expected dialog transition. Do not resolve `VODForge` by application name:
multiple old QA bundles can share that name and launch the wrong app.

```sh
PYTHONPATH=engineering-quality .venv/bin/python -m quality_harness.native_input \
  --session <journey>/session.json --window-title '<exact current title>' \
  --output <journey>/input-001.json observe
```

Use a fresh output filename for each command. `click` requires `--x`, `--y`,
`--image-width` and `--image-height` in the same displayed image coordinate space;
the driver converts those pixels to desktop points once. Never mix resized image
coordinates with Retina pixel dimensions or a different window's bounds. `key`
accepts `--code <macOS virtual key>` and optional `--command` and `--shift`. For opening Settings,
add `--expect-window 'VODForge Settings'` before `click`; when closing it, target
Settings and add `--expect-closed --expect-window '<main title>'` before `key`.
Use `text --value '<fixture text>'` for native Unicode typing without replacing
the user's clipboard. Text is not copied into the input receipt.
Native file pickers can expose an AXSheet instead of AXFocusedWindow. The driver
accepts only one sheet with an exact same-PID native rectangle match. Discover the
actual picker title, then use Command-Shift-G (`key --code 5 --command --shift`),
native text entry, Return to select the path, and Return to open the selected file.
Observe the sheet transition before proceeding; do not assume a dispatched key worked.
The expected transition must be observed before the next input. If focus differs,
inspect the named window rather than sending keys to any window with the same PID.

The input receipt reports dispatch, not feature success. Inspect its screenshot,
then use the existing `record-e2e-event` to record a passing observation. A timeout
must retain the failed receipt and must not automatically resend a click or submit
a run again. Native input diagnosis may use an isolated source probe; it never
substitutes for final signed-artifact evidence. Validate a driver correction with
a short repeated dialog/entry cycle before spending another full telemetry journey.

Window identity alone does not prove that a click can reach it. The driver uses
desktop accessibility hit-testing to refuse points covered by another application,
including notifications. Move the isolated QA window clear using native window
controls; do not change the user's notification preferences. Native NSAlert windows
use layer 8, so include those in the input inventory and target their exact title
before returning to the main window. Main-window provenance remains layer 0.
The driver captures the actual desktop rectangle: `screencapture -l` can capture
an attached window group whose image size differs from the selected dialog's bounds.
On failure inspect the accompanying local desktop capture before another attempt.
Desktop captures may contain unrelated private content and must not be published.

Run producer/lifecycle regressions and targeted native reproductions before building
the next signed candidate. After a runtime fix, first repeat its failing case on
the new artifact; do not spend another full journey before checking that fix.
Preserve rejected artifacts and evidence, but never reuse their receipts as proof
for a replacement artifact.

Use the session's dedicated `slow_input_url` only for cancellation and
`queued_input_url` only for queue advancement. They are deliberately distinct from
the earlier export/preset source, so an existing valid output cannot turn the
first cancellation test into an immediate cache hit. The packaged fixture uses
250 ms per 16 KiB slow-media chunk; ordinary repository scenarios retain their
fast default. Do not wait until completion to capture an active state. Capture
immediately after submission, inspect the image, and require both a real active
run and a queued card before testing cancellation. If a dedicated case was already
completed, preserve its output and use a fresh isolated destination for that case;
do not repeatedly submit a cached source and call it a transfer test.
The recorder checks the existing run journal for active work owned by the current
PID, and for a pending job at the queued checkpoint. This is additional evidence;
it never replaces the required native screenshot or proves visible progress alone.

Select the canonical description-stress export before any other Library item.
The packaged app writes its immutable geometry receipt for the first selected
item in each launch. Record `library_description_observed` immediately: the
recorder validates the receipt's item, description, launch and geometry at that
point, rather than discovering a mismatch after the rest of the journey. Preserve
a rejected receipt; never overwrite it or treat a later screenshot as its repair.

Before each native dialog action, discover the current window owned by the
attested PID and use its exact title and current bounds. Opening a dialog and
acting inside it are separate steps: verify it is visible first. After one failed
targeting attempt, inspect fresh native state and correct the target instead of
repeating the same coordinates. Bound a window-readiness wait to five seconds;
retain a timeout as an automation failure, not an application failure or passing
observation. Never relaunch the whole candidate solely to recover window focus.

Keep a per-platform action ledger as actions occur, including extra attempts,
cache reuse, retries, and failures. Reconcile preview D1 after each feature group
so a missing producer is discovered before the remainder of the journey. Stop
repeating a failed step after two attempts and diagnose the fixture, recorder,
or product owner with retained evidence. Continue independent required checks.
Report a delay or blocker promptly rather than allowing hours of silent retries.
These limits bound wasted retries; they do not waive any release prerequisite.

Use the recorder's `telemetry` profile, which requires native screenshots for all
producer actions and refusal/disabled observations. Follow its ordered event list:
complete the media actions during the first session, reopen, then capture the
same-version and completed-event readbacks before the negative checks. The
checkpoints below describe the assertions, not an alternate recorder order.

The trace binds the main feature journey to launch 1, same-version reopening to
launch 2, saved-consent refusal after reopening to launch 3, and explicit
telemetry-disabled operation to launch 4. The last launch must attest both preview
and production telemetry disabled. Retain the first pre-restart media/history
snapshot through all three reopenings. Negative checks should use existing media
and controls without changing the Library or exporting additional files.

The telemetry profile validates MP4, MP3 and Original audio together, including
both supported Original audio extensions (`.opus` and `.m4a`). Every retained
output must have matching history, type, extension and an unchanged media hash;
only the designated long-description fixture must retain the sentinel description.
The ordinary smoke/deep profiles retain their strict MP4 and description contract.

Retain the UI action ledger, screenshots, exact candidate archive/executable hashes,
process launch identities, source commit, platform, and raw scoped D1 checkpoints.
A helper directly posting events is a transport test, not packaged journey proof.

1. Fresh isolated profile: decline or leave permission unknown; verify no optional
   telemetry rows and capture `unknown.json`. Grant permission through the UI. Observe one installation and
   credential, first launch and app-open event. Capture `first_launch.json`.
   Leave the app idle until this delivery completes: a later feature action must
   not be needed to wake the app-open queue. Require exactly one app-open event at
   this checkpoint, and exactly two at `same_version_reopen.json`. Startup retries
   must drain an existing immutable event after a transient delivery failure;
   recording while an empty delivery worker exits must not strand the new event.
2. Quit normally. Reopen the **same version and same profile** after the timestamp
   second changes. Verify last seen advances; first launch, creation date, identity
   and current version stay fixed; no update event appears. Capture
   `same_version_reopen.json`. Repeated UI callbacks within one session must not
   create extra app-open events or conflicting retransmissions after the first
   app-open event has already been delivered and removed from the outbox. Check
   the app diagnostics as well as D1 counts; a server-rejected duplicate is not
   correct client-side session deduplication.
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
Try it when enabled for the candidate, Technical view, appearance changes, and update/Repair outcomes. UI action
and expected counts must be recorded before reading D1, never inferred from rows.

For fragmented downloads, verify Cancel and Skip while a fragment is in flight,
then verify queued work advances and the isolated output has no `.vfstage`
residue after clean exit. The provider operation must close its fragment
destination before staging cleanup; garbage collection or deleting leftovers
from the test driver is not proof. Preserve any failed receipt and its files.

After Custom, close and reopen Settings at its normal dialog size, then switch
back to Everyday using the preset menu. Verify the complete control is visible
and the selection commits on both platforms. Merely selecting Custom last in a
preset loop does not cover the expanded layout or the return path. The native
`test_task_presets_use_real_dropdown_and_custom_quality_controls` regression
exercises that reopened state as part of the existing repository gate.

For organization, independently edit and save a note, tags, and a category, then
verify all three saved values locally and all three action names in D1. Keep
private sentinel values out of the telemetry rows. A dialog screenshot or a direct
`record_feature` test alone cannot prove that its actual save callback emits each
action. The repository gate includes all field create/clear/unchanged/failed-save
cases in `tests/test_telemetry_features.py`.

For playback failure, back up a media file inside the isolated QA profile and
deny read access using the platform's file permissions. Start playback through
the real player and require `player/failed`, with no completion attributed to
that failed attempt. Restore the original bytes and permissions, then verify
successful playback in the same player window: capture `Playing` with advancing
position before eventual completion. Also replay after a normal ending and
require advancing playback again. Retain the provider error and UI evidence: libVLC can emit
`MediaPlayerEncounteredError` while its later polled state is `Ended`. A zero-time
Ended display is neither failure-path nor recovery proof. VLC 3 can accept
`play()` on an ended input without restarting it; replay must reset that input.
The backend/UI regression in
`tests/test_libvlc_backend.py` covers this transition and retry reset in the
repository test gate.

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

For both platform handoffs, assert the current telemetry permission is passed to
the detached helper for normal updates and Repair. Cover consent allowed, denied,
and an absent telemetry owner in the real UI handoff callback regression. In the
native preview journey, retain the original helper receipt and require
`telemetry_permitted: true` for an opted-in update before accepting its relaunch
event. A successful installation alone cannot satisfy this telemetry gate.

For a release whose canonical SHOWCASE_MODE is none, verify both announcement
surfaces remain absent on fresh and returning profiles. The verifier excludes
their unreachable actions and rejects any announcement event instead. Keep
evergreen owner/native regressions for future enabled showcases. The combined
announcement/guidance/appearance screenshot checkpoint must show the silent
release state plus the enabled guidance and appearance interactions.


## Isolated updater feed before publication

The public updater still uses only the official stable GitHub feed. For the
pre-publication journey, serve the final signed artifacts on the same QA machine:

```sh
PYTHONPATH=engineering-quality .venv/bin/python -m quality_harness.update_fixture \
  --version 0.2.2 \
  --asset /absolute/path/VODForge-macOS-arm64-v0.2.2.zip \
  --output build/qa-update-feed
```

Use the matching Windows installer on Windows. Set `VODFORGE_QA_UPDATE_FEED` to
the URL in `feed.json` **before launching** the isolated packaged app. The feed
requires packaged preview mode, the private preview key, isolated HOME/TMP/profile,
and an executable inside the isolation root. Other hosts, redirects, proxies,
external asset URLs and ordinary installed profiles are rejected. Normal launches
without this variable retain the official feed. Never modify the signed artifact.
The detached Windows Repair helper receives only the already validated feed;
it retains size/hash, timestamped publisher, exact target and relaunch verification.

For the first release introducing preview routing, build a separately identified,
signed QA baseline from the same source at the preceding registered version. This
is a QA baseline, not the historical public binary. Retain its hash/version and
preview snapshot, then click the normal update UI to install the exact candidate.
Keep the separate actual-public-baseline installer/legacy-helper checks too; the
QA baseline does not replace that compatibility evidence.

On the final candidate, create `unavailable` in the feed output directory to return
real HTTP503 responses, click Check for updates and observe the actionable failure.
Remove that file, then click Repair VODForge. The normal Repair path downloads,
verifies, installs and relaunches the same final candidate. Capture preview-D1
failure, repair and verified relaunch observations. Retain `feed.json`,
`requests.jsonl`, the original helper receipts and actual UI captures. A changed
fixture artifact returns409; do not rewrite its checksum or receipt to hide a change.

The feed is a local test provider, not GitHub availability evidence. Regression
coverage executes both Python and PowerShell transports against real loopback
responses, including escaped URLs, redirects, checksum failure and normal-context
refusal. No test bypasses installer publisher verification.
