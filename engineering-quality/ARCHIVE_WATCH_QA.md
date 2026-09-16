# Archive, Watch and embedded player validation ledger

Status: local source candidate under review; not release qualified. Desktop branch
codex/archive-management; backend branch codex/archive-watch-telemetry.
Only synthetic fixtures are used. User Downloads/NAS media is not scanned,
moved, hashed or deleted.

| Feature / invariant | Maintained regression and class harness | Telemetry |
| --- | --- | --- |
| Archive roots, ancestry, exact saved location, lexical Windows/UNC/POSIX | test_archive_models, test_archive_relink, test_archive_ui_owners; real Tk test_archive_native | archive navigation; archive_location_operation requested/actual outcome/cancel/timeout |
| Relink preview, collisions, stale review, write failure, cancellation before/after save | test_archive_relink; real files, independent disk reload and bounded lane schedules in test_archive_lifecycle | archive_relink_operation requested/verified/commit_requested/cancel_requested/committed/failure/stale/cancel/timeout; aggregate counts |
| Concurrent history writers and bounded close | test_history_pending, test_archive_lifecycle; forced-close restart recovery, save/retirement/read errors, limits, coalescing and replay ordering | archive history_deferred/history_recovered; existing consent/outbox authority |
| Watch playlist rails, channel drilldown, unlisted saved videos, singleton layout and variants | test_archive_models, measured native geometry/keyboard/count contracts | watch opened/mode/channel/search/rail/details/singleton |
| Canonical selection, variants, annotations and source metadata | test_library_state, test_library_projection, test_library_annotations, migrated state-authority contracts | archive version/inspection actions; no note/tag/title payloads |
| Artwork background work and owner retirement | test_archive_artwork, test_archive_work; bounded worker and late-result rejection | artwork_loaded/unavailable with counts and time bucket |
| Embedded player and Back context | test_archive_ui_owners, existing playback lifecycle matrix; actual MP4/MP3/M4A source-native tests | existing playback_operation with library/watch origin and embedded/window surface |
| Teardown, same-path refocus, immediate replay observation | native final Tcl drain, real paused refocus, provider completion/replay; exact successful lsof result | playback ready/started/focused/completed/closed; observation failure cannot prevent cleanup |
| Privacy, consent, duplicate/stale delivery and backend retention | test_archive_telemetry, cross-owner tests, enrolled Worker/local D1 tests; vocabulary parity checks feature/dimension/operation definitions | existing ProductTelemetryOwner is the sole consent/outbox/transport authority |

Evidence directory: /Users/coop/Dev/vodforge/build/archive-management-20260916.
ARCHIVE_BASELINE_PARITY.json maps all 49 baseline capabilities with explicit
per-capability gaps. It is a map, not 49 accepted native results.

## Final current checkpoint: 2026-09-16 18:48 UTC

- archive-affected-final-current.log: **836 passed in 7.21s**.
- archive-full-native-v3-completion.json/XML: **178 passed in82.95s**,
  zero skips/failures/errors; source stable, changed_files empty. This is the
  maintained native_surface_contract including all existing UI families plus
  Archive, Watch and actual libVLC playback.
  Freeze source-freeze-20260916T184436Z; manifest SHA256
  a9a3f6dbe9c8a1be8cb94f908907ff27112b2a3dddf56caad6f2f22cd1309e69.
- Focused v7: **23 passed**. Relink file/folder commit, preview cancel, stale
  review, filtered view plus journaled front insertion retain the exact owner
  after the numeric index changes. Relocated missing-media recovery invokes
  real Tk actions; fixture chooser/queue boundaries prove accept/cancel without
  starting downloads or changing the default destination.
- archive-backend-artwork-final.log: **44 passed** against local Worker/D1;
  archive-parity-artwork-final.log: vocabulary parity passed, including bounded
  history_defer_failed/history_recovery_failed observation producers.
- archive-mutation-final-current.log: copied baseline41pass, **5/5 detected**;
  collection/setup/skip/timeouts cannot qualify as detection.
- Scoped Ruff42files and mypy89files clean. The maintained headless matrix now
  includes the three true child-process interruption/restart cases in
  engineering-quality/tests/test_history_process_recovery.py.
- archive-final-native-cleanup.json: runner61433/pytest61434 no longer exist;
  three real-provider roots destroyed, no Python/Tcl errors, successful raw lsof
  probes with no synthetic media handles. GUI lease explicitly returned.
- Root independently accepted the bounded journal/activity milestone using
  64passing cases, including SIGKILL at accepted-journal and saved-before-retirement
  boundaries and fresh-interpreter readback. This is process-interruption
  evidence, not a power-loss/fsync guarantee.

Additional fail-before evidence:
- archive-artwork-refresh-before.log: three failures for replaced/late/removed
  thumbnails. Known thumbnail file stamps are now checked off the UI thread
  every30seconds only for visible requests; unchanged pixels are not decoded.
  Tests prove24-request batches,48visible requests,64images and bounded256-key
  retained metadata. Hidden/closed owners do not keep probing.
- archive-selected-artwork-before.log: same-owner metadata replacement retained
  stale pixels. Metadata identity plus current selection now rejects stale
  results, invalidates old remote generations, and retains latest optional
  selection while the one storage lane is busy.
- archive-native-real-v5.log:17pass2fail. Relink committed successfully but
  lost selection when path ownership became archive ownership. The correction
  follows the actual committed row's stable owner across deferred insertions.
  v6 19pass and v7 23pass confirm the relevant native cases.
- archive-full-native-v1:175pass3fixture failures. Fixtures now reveal the compact
  inspector and actual Description tab and initialize the constructor's poster
  field. Full-v2 passed178; the final v3 also uses real multiline descriptions
  and dlineinfo bounds to prove the last content line is visible.

## Earlier verified checkpoints


- Latest affected gate: archive-affected-activity-corrected.log,
  **822 passed in 6.51s**. Activity lineage patch has clean scoped Ruff and
  mypy89; history-journal-activity-audit-freeze.json binds all10 affected files.
  **Native v4 predates this final activity ownership correction.**
- history-activity-relink-after.log:70 focused tests; independent unchanged
  activity-relink probe4/4 passes in history-activity-root-probe-after.log.
  history-activity-relink-before.log preserves4 real failures:2 missing latest
  activity after relink and2 same-run variant spill controls. The existing
  DownloadJob now retains exact accepted owners and follows archive lineage;
  foreign runs and unrelated variants remain unchanged.
- Existing maintained bounded_mutation_history gate now enrolls journal staging
  and restart replay, with baseline41passes and **5/5 mutants detected**.
  archive-mutation-maintained.log and maintained-mutation-v1 retain every result.
  Ten gate tests reject collection/setup errors, skipped evidence, timeouts and
  unavailable runners as mutation kills. Earlier direct forced-close mutation
  proof remains separately retained.


- archive-affected-journal-corrected.log: **808 passed in 6.42s**. The prior
  archive-affected-journal.log retains 807 passes and one obsolete fake-player
  fixture missing the extracted _present_snapshot binding. That fixture now
  invokes the real method; failure/started/completed assertions are unchanged.
- archive-pending-order-after.log: **53 passed**, history and class lifecycle.
- archive-backend-journal.log: **44 passed**, actual local Worker/D1 tests.
  archive-parity-journal.log: desktop/backend feature, dimension and operation
  correlation vocabulary parity passed.
- Scoped Ruff: 37 files clean at the native freeze; mypy: 89 files clean.
- archive-native-real-v4.log/XML: **13 passed in 22.46s**, source stable.
  Freeze source-freeze-20260916T181208Z; manifest SHA256
  a079435a8b0db5e98f8000fc64822f9b244a7bd1e2b2caeb56d92575dc4a8c94.
  Native interval 18:12:08–18:12:31 UTC. Kryden confirmed no overlapping
  native app; lease returned, runner exited, all roots destroyed.
- native-real-v4/actual-{mp4,mp3,m4a}-receipt.json: real libVLC decoding,
  audio buffers, MP4 display counters, all five FFmpeg Preview Moments,
  canonical annotation dialog/save/reload, seek/chapter/heatmap/replay/volume,
  paused same-path refocus and Back. Watch mode/channel/query/page/rail offsets
  and nonzero scroll are unchanged after Back. Every lsof probe has returncode
  zero, a matching PID header and raw stdout/stderr retained; no fixture handles.
  All Python callback and post-destroy Tcl error arrays are empty.
  **Physical input and observed audibility remain false.**
- history-journal-audit-freeze.json binds the journal, UI writer, app and test
  hashes for independent review. No production file changed after native v4
  through that checkpoint; only the old backend-test fixture was repaired.

## Defects caught and negative proof retained

- models-worker-before.log: provider IDs merged across providers and activity
  order changed. Corrected tests preserve canonical ordering and distinct owners.
- archive-peer-cancel-before.log: alias collision overwrote cancellation or
  deadline outcomes. Collision cannot replace an already-retired result.
- relinked-recovery-before.log: relocated saved profiles failed recovery.
  Validated original settings now survive; a new destination is required and
  cancelling does not queue or change defaults/history.
- event-pump-fixture-corrected-before.log, native v4-era raw errors: late root
  timers survived teardown. Event pump, startup and receipt timers now retire;
  later exact native runs include a final Tcl drain.
- archive-native-real-v1.log: paused same-path focus silently restarted media
  and duplicated polling. Refocus and repeated show are now idempotent.
- archive-native-real-v2.log: immediate replay reset Ended before completion
  was observed. Toggle and poll now share actual-snapshot presentation.
- Original independent coordinator forced-close probes are preserved at
  /Users/coop/Documents/Codex/2026-09-16/coordinator-audit/vodforge-archive-close-deadline/.
  A bounded pending-delta journal now merges onto actual committed history at
  settlement/restart, instead of writing a stale whole-history snapshot.
- archive-pending-order-before.log: two real failures showed early journal
  data overwriting newer callback data. Replay now precedes live callbacks.
- mutation-drop-pending-journal.log: in-memory removal of durable staging is
  caught by **both** forced-close restart cases (verification and post-save
  acknowledgment boundaries). No source mutation remains.
- mutation-discard-durable-ack.log: dropping the committed result after cancel
  is caught by the generalized durable-outcome matrix. Earlier
  archive-mutations.json also catches false-save-success and retired reads.

## Remaining acceptance

- Settled seek/capture consistency: v7 Moments capture shows provider frame6s
  while transport label remains4s. The fixture waited for provider position,
  not for the next100ms UI poll, so a transitional capture is plausible. A future
  playback qualification must wait/assert provider AND transport consistency;
  this screenshot alone is not classified as a product defect.

- Complete integrated 49-capability Library/shared action parity.
- Physical OS folder chooser, native delayed/cancelled commit UI and actual
  storage reconnect. Current native tests exercise real Tk actions with bounded
  chooser/queue seams; real-file class tests cover underlying commit schedules.
- Artwork refresh and cache limits pass source tests; physical-device storage
  reconnect and long-duration native performance remain separate tiers.
- Windows native/UNC and real NAS offline behavior; Mac/Windows foreground
  physical resize, CPU/heartbeat and exact packaged journeys.
- Independent final integrated49-capability acceptance; the map does not turn
  all baseline controls into manually accepted journeys.

These source/native checks do not qualify a release or prove physical input,
audible output, Windows behavior or packaged behavior. Production backend
deployment must precede a future client release; no deployment, push, merge,
app replacement or release has been performed.
