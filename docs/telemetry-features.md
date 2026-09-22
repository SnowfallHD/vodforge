# Product telemetry ownership and feature contract

Optional analytics measures feature use and outcomes. It does not collect media
URLs, IDs, titles, paths, filenames, queries, notes, tags, category names, playback
positions, raw colors, GPU identifiers, or error prose. Consent, artifact policy,
preview isolation, immutable credentials and bounded retention still apply.

## Owners

| Responsibility | Owner |
| --- | --- |
| Closed feature/action and dimension vocabulary; bucket/projection policy | `yt_downloader/telemetry_features.py` |
| Event names/schema, installation-scoped attempt IDs, consent, session engagement deduplication, timing and retry outbox | `yt_downloader/product_telemetry.py` |
| Authentication, launch authorization and transport retry | Existing `telemetry_credentials.py` / `telemetry_transport.py` |
| Actual feature actions and outcomes | Existing Library, player, conversion, showcase and update UI owners; app composes callbacks |
| Update outcome receipts and current-executable confirmation | Existing `updates.py` helper and receipt functions |
| Validation, compatibility and immutable D1 storage | Site `product-telemetry.ts` / `enrolled-telemetry.ts`; migration 0015 |
| Local cross-language/HTTP/D1 contracts | `quality_harness/telemetry_checks.py` |
| Fixed remote preview serializer probe and final-artifact release evidence | `telemetry_feature_probe.py` and `telemetry_release.py` respectively |

Do not add another event dispatcher or run-state owner. New features use callbacks
at the existing authoritative success/failure boundary. Export fact projection
belongs in the vocabulary module, not widget handlers. The backend harness fails
if Python and TypeScript vocabularies drift. The provider reuses the desktop event
names and dimension validator rather than maintaining its own event catalog.

## Schema v2

`attempt_id` is derived from the installation's random identity and the local run
key. It exposes neither the local key nor the source. `retry_of` references the
previous opaque attempt. The existing run journal preserves explicit execution and retry links. A playlist
item presentation can belong to a parent execution without itself being a retry.
No second attempt registry is introduced. Different installations
produce different IDs for the same local key.

Runs emit start and terminal events; `run_completed` distinguishes `complete` and
`partial`. Queuing, removal before start, actual item skip, and each validated media
commit have separate events. A playlist has one attempt and multiple media exports.
`run_skipped` records an item skip, not an additional terminal outcome for the
whole attempt. Skipping its last item can therefore also produce `run_stopped`
when the enclosing run finishes; do not sum item skips into run terminal counts.
Recovery of interrupted attempts reports the persisted terminal state. A closed
app that never reopens cannot report a crash outcome.

Exports report the preset, successful command's encoder and rate-control mode,
source/output resolution tiers, duration and size buckets. Original audio reports
`original` / `copy`; an MP3's embedded cover does not count as video resolution.
MP3 artwork uses `none`, `thumbnail` or `custom`, never an image path. Input kind
and known URL-list size are bounded. Unknown playlist length is omitted rather
than reported as one item. Local conversion emits starts, failures, cancellations
and canonical-history-confirmed completion with measured output dimensions.

Processing time means elapsed worker time, including download/validation/commit;
queue wait is separate. Timings use a monotonic clock in the telemetry owner and
are omitted when their start was not observed in this process. They are not
encoder-only benchmark measurements. The outbox remains limited to 256 events,
512 KiB and the existing 30-day delivery acceptance window.

Deduplication suppresses new event creation, not delivery retries: repeated
startup or feature callbacks retry any existing immutable queued event. A producer
request received while the delivery worker is finishing must wake that worker or
start its replacement. The release journey requires app-open delivery while idle,
before a later feature action could mask a stranded queue.

Library discovery/organization, player controls and completion/failure,
missing-media recovery, announcements/Try it, Technical disclosure and appearance
use `feature_used` with a closed feature/action pair. Engagement records presence
once per permitted process session/action, not every keystroke or polling tick.
Search and annotation text is never an event field. Theme names are enumerated;
a custom accent is represented only as `custom`.

Organization events compare the typed annotation's `note`, `tags`, and `category`
after a successful save. Adding or clearing a value counts as a change; saving
unchanged values or a failed write does not. The save-callback regression covers
each field independently, including refusal of private values in event arguments.

Playback failures follow the provider's error event even when libVLC subsequently
reports `Ended`. The existing playback backend retains that error until a new
load or retry; the player reports failure rather than completion. Provider
callbacks do not wait on the lock used by native playback operations.
Replay after failure or completion reloads the same local media through the
existing native-safe load path, because VLC 3 can accept `play()` while leaving
its ended input idle. Release evidence must show advancing playback after retry
and normal replay; an `Ended` label at zero seconds is not successful recovery.

Updater actions are individual observations. Download, handoff, failure stage,
relaunch and repair are distinct. A successful relaunch requires a helper receipt
and matching executing bytes. Failed Windows handoffs retained after Later can be
reported on the next open of that exact app target. Original helper receipts remain
untouched; a companion marker means the observation was queued in the existing
outbox, not that D1 delivery succeeded. Permission must have been enabled at the
handoff and still be enabled when reporting; later consent cannot backfill an
update started with analytics off. If permission is withdrawn before observation,
a per-action discarded marker prevents a later opt-in from backfilling that result.

## Compatibility and release order

Keep schema v1 ingestion and outbox replay for older released apps. Never relabel
legacy null formats or invent old attempt relationships. Deploy the additive
compatibility migration and backend before publishing a schema-v2 desktop release.
The production deployment and app release are separate from preview testing.

Every addition requires: closed-field privacy rejection tests; a real producer
regression; outbox/retry/consent coverage; backend normalization and D1 readback;
and native action evidence in both final signed release artifacts against preview
D1. See [the release gate](../engineering-quality/TELEMETRY_RELEASE_GATE.md).
A direct serializer probe is deliberately labeled source/transport proof and
cannot satisfy the packaged release gate.

## Diagnostic richness (next client release)

Existing failure_detail now carries closed failure_code values, bounded format/video/audio counts and TLS verification codes. No raw exception messages, URL, media identifiers, cookie/profile identity or commands are uploaded. The source-selection exception owns format counts; the diagnostic owner traverses wrapped causes. Existing attempt events include cookie access, provider category and encoder preference/architecture.

Settings snapshots use the existing consent-gated feature event pipeline on app open, successful debounced saves and cookie-source changes. Every persisted preference has a tested explicit privacy decision: output directory, custom color and announcement state are excluded; processing choices, local output profile and appearance choice are allowlisted. Bitrate values are bucketed; CRF is bounded. Snapshots deduplicate only unchanged states, retaining A-B-A transitions. Browser names, profiles, cookie files/contents, tags and input content never leave the device. Existing per-session engagement counts remain such; they are not click-by-click traces.

Investigation: order events by installation/time, join attempt_id/retry_of, compare failure_code/counts and attempt settings, then compare nearby settings snapshots and outcomes. Changing cookies followed by success is evidence of a possible access-discoverability problem, not proof of causation or proof separate attempts used the same video. Missing fields on older clients mean not recorded, never false/zero. Raw logs and source URLs still require voluntary support sharing if structured evidence cannot reproduce an issue. No guarantee all bugs can be diagnosed automatically.

Deploy the compatible backend validator before publishing the new client. Test with the focused diagnostic regressions and existing preview-D1 feature probe. No migration, second telemetry store or transport required.

### File-operation outcomes

library_file_operation reports requested, started, completed, needs_attention and
cancelled through the existing consent/provenance-gated operation owner. file_action
is limited to move, delete or recovery. Counts use the existing bounded numeric
dimensions. A displayed recovery outcome never fabricates success after an
uncertain write. Paths, filenames, volume labels, selected owners, descriptions,
receipt contents and raw OS errors are excluded. Client and ingestion schemas share
the same closed actions/dimensions; source/native producer checks are separate from
production delivery and no telemetry service is deployed by the private UI work.

## Startup download recovery

The recovery owner now retains a bounded typed startup cause until telemetry is
initialized. Reporting requires consent at the failure and current consent in the
same collection epoch. Later opt-in does not backfill the startup failure.
run_recovery_operation links the initial failure to a later blocked-start action
using a random operation key; a new attempted run uses the existing opaque,
installation-scoped attempt identity. The original failure carries bounded machine
facts; blocked-start carries the retained cause/stage and does not invent another
exception. Raw exception text, journal content, URLs and paths stay local.

Cause fixtures exercise malformed JSON, schema mismatch, live owner refusal,
staging validation, read/write access, cleanup failure and queue loading. Python
producer payloads are replayed through authenticated v2 ingestion and asserted
against exact D1 cause/context rows, with duplicate retries and privacy rejection.
These tests are local verification, not evidence of deployed backend or released
desktop support. Existing users may still need local diagnostics. The September
18 missing-safe-retry-URL report was diagnosed from the user's startup log;
the first later YouTube request did not cause that earlier startup failure.

Recovery-only deserialization now allows retained attempts with no retry URL,
while executable queue jobs remain strict. A non-retryable historical attempt
does not justify blocking unrelated fresh downloads. Process ownership, staging
boundaries and safe cleanup still apply. Do not fabricate source links or delete
a user's journal to satisfy a telemetry or recovery test.

The full-application telemetry acceptance pass is required and remains open;
see engineering-quality/HARNESS_GUIDE.md for its lifecycle coverage and evidence
requirements. No catalog count establishes complete diagnostic coverage.


### Runtime journal admission and queue updates

Refused active-run admission and queue writes emit run_recovery_operation failures
with the existing closed cause/stage/disposition contract. Each refusal has its
own operation identity; repeated intents for the same run retain opaque attempt
correlation. Observation never changes journal atomicity, marks healthy startup
recovery unavailable, or prevents the next valid intent.

The bounded recovery_entry dimension identifies startup, run_admission, or
queue_update. Absence on older events means unknown; do not infer it retroactively.
Exception text, source links and paths are not payloads. Disabled consent records
nothing. Observer and diagnostic failures preserve the original refusal. Actual
producer fixtures exercise authenticated local ingestion, stored fields, duplicate
requests and malformed/private context rejection. Production deployment and
exact-package delivery remain separate.


### Query utility and denominator limits

To answer "which recovery entry points refused work, and why?", group observed
refusal operations separately from affected attempts. Scope platform, release and
time explicitly before comparing runs:

~~~sql
SELECT
  coalesce(json_extract(dimensions, '$.recovery_entry'), 'legacy_unknown') AS entry,
  json_extract(dimensions, '$.recovery_cause') AS cause,
  json_extract(dimensions, '$.recovery_stage') AS stage,
  count(DISTINCT json_extract(dimensions, '$.operation_id')) AS refusal_operations,
  count(DISTINCT attempt_id) AS affected_attempts
FROM product_events
WHERE feature = 'run_recovery_operation' AND action = 'failed'
  AND platform = :platform AND app_version = :version
  AND release_channel = :channel
  AND occurred_at >= :since AND occurred_at < :until
GROUP BY entry, cause, stage;
~~~

The enrolled backend query control ingests the actual repeated-refusal producer
fixture, replays both deliveries, and verifies two refusal operations for one
affected attempt. A retry of delivery must not inflate either count. Missing
attempt IDs do not contribute to affected_attempts; preserve that limitation when
interpreting startup failures.

This is a count of observed refusals, not a failure rate. This event family does
not yet supply all successful admission intents as a denominator, and no event
can describe consent-disabled populations. It also cannot by itself prove that
a later successful download resolved the same refusal. Keep those coverage and
correlation requirements open in the full telemetry inventory.


### Presentation audit scheduling delay

The presentation_operation producer reports lag_measurement=ui_pump_delay.
This measures how late the UI event loop runs a scheduled audit, relative to that
audit's due time. Repeated resize/render updates coalesce into the existing
pending audit and preserve its original due time. Replacing the operation retires
the pending timer and starts a new deadline, so the new owner does not inherit
the preceding operation's delay.

A regression reproduced a 320 ms pending audit reported as under_50ms because
each update replaced the due time. The corrected queued-clock oracle preserves
the delay and includes a fresh-owner positive control. A real Tk controlled-pump
test exercises the production probe and local outbox; its public payload is
exported through the production parser/serializer to the backend fixture
test/fixtures/presentation-audit-wait.json. The enrolled backend suite verifies
authenticated acceptance, exact stored dimensions, duplicate delivery, and this
query's distinct-operation count:

~~~sql
SELECT json_extract(dimensions, '$.lag_bucket') AS lag_bucket,
       COUNT(DISTINCT json_extract(dimensions, '$.operation_id')) AS sampled_operations
FROM product_events
WHERE feature = 'presentation_operation'
  AND action = 'observed'
  AND json_extract(dimensions, '$.lag_measurement') = 'ui_pump_delay'
  AND app_version = ?
  AND platform = ?
  AND occurred_at >= ? AND occurred_at < ?
GROUP BY lag_bucket;
~~~

Use a declared version/platform/time scope. These are sampled audit observations,
not all user interactions, FPS, compositor latency, or a failure-rate denominator.
An operation can contribute to more than one bucket if it has multiple observed
states; do not sum bucket counts as distinct operations. Budget limits, consent
and missing delivery exclude populations. Pending audit delay is distinct from
audit execution cost (presentation_audit). Historical clients that reset due
times cannot support the corrected interpretation retroactively.

Reproduce the native fixture with VODFORGE_NATIVE_UI_TESTS=1 and a fresh
VODFORGE_NATIVE_EVIDENCE_DIR while running the coalesced_audit test in
tests/test_presentation_native.py. Review and copy its generated
presentation-audit-wait.json to the backend fixture path, then run
test/enrolled-telemetry.spec.ts. Keep the earlier raw fixture and receipt alongside
the new source binding. This is local source/transport evidence; packaged and
deployed ingestion still require their own journeys.

## Run-menu command admission

run_control_operation reports admitted or rejected for cancel, skip_item and
skip_source at the active-run menu commit boundary. Required closed dimensions
are run_control_action, run_control_origin=run_menu and run_control_owner
(current for admitted, retired for rejected). Each invocation uses the existing
random operation correlation and consent-bound outbox. No run key, URL, title,
path or raw input enters these observations.

Admission means the command still belongs to the active execution. It does not
prove the worker stopped or an item was skipped; terminal and skip events retain
their existing meanings. Missing or failed telemetry must not change admission.

Group stored events by action and run_control_action and count distinct
operation_id. The denominator is observed menu commit attempts (admitted plus
rejected), with delivery replay deduplicated. This excludes menus abandoned
without selection, other control surfaces, consent-disabled use and observations
lost to outbox/transport limits. It is not a cancellation success rate. Tests
cover real producer/outbox consent and observer failure, authenticated local
ingestion, exact stored dimensions, replay and contradictory/private payload
rejection. Local backend qualification is not production deployment.

Watch details_retired records that a View in Library menu command found its
original media subject removed. It uses the existing once-per-consenting-session
engagement path with no dimensions or private content. Actual callback/outbox
and authenticated stored replay tests cover the signal. It establishes presence
of this stale-subject outcome, not its frequency, all menu abandonment, or a
successful navigation denominator.

## Resize burst origin and query limits

The existing resize observer records the view and library-size bucket when the
first changed window geometry starts a consented burst. That context stays with
the operation through delayed pump settlement, even if navigation or history
changes meanwhile. Watch is an explicit supported view. Unknown view names
become the bounded unknown value; content and arbitrary labels are never sent.

The old producer read context at settlement and omitted Watch from its local
allowlist. Six original-view/replacement regressions failed before correction.
The maintained tests/test_resize_observation_owner.py now exercises the actual
geometry and pump producers through the real consent owner and offline outbox,
plus denied/withdrawn consent, closing, unchanged geometry and repeated pumping.
Its six exported payloads feed authenticated local backend ingestion, exact
stored readback, duplicate delivery and this distinct-operation query:

~~~sql
SELECT json_extract(dimensions, '$.view') AS origin_view,
       json_extract(dimensions, '$.lag_bucket') AS pump_delay,
       COUNT(DISTINCT json_extract(dimensions, '$.operation_id')) AS settled_bursts
FROM product_events
WHERE feature = 'resize_operation' AND action = 'settled'
  AND json_extract(dimensions, '$.lag_measurement') = 'ui_pump_delay'
GROUP BY origin_view, pump_delay;
~~~

This counts delivered, consenting, settled geometry bursts by their starting
view. One burst may span navigation and multiple geometry changes. It does not
measure physical gesture count, frame rate, compositor latency, pointer release,
or all attempted resizes. Denied consent, shutdown before settlement and
undelivered events are absent, not zero-delay observations. Existing historical
events retain their older semantics; do not retroactively relabel unknown rows
as Watch. Use exact qualified build identity when comparing producer versions.

The producer regression is discovered by the existing whole-tests static suite;
backend readback is in enrolled-telemetry.spec.ts under the existing backend
suite. These controlled-clock source tests do not certify native resizing or
complete temporal evaluator enrollment.

### Player callbacks after close

Seek, chapter, preview, timeline and volume callbacks are admitted only while
their MediaPlayerWindow owner is open. Retired callbacks must not emit successful
feature usage or send provider commands. Closing remains on the existing closed
operation path; this repair adds no passive-focus or late-input event.

The native retirement matrix asserts the feature callback boundary remains
unchanged after close and verifies valid live provider admission first. This is
local suppression evidence, not additional producer-to-backend readback coverage.
Physical gesture timing, all playback adapters and full telemetry qualification
remain separate. No new event schema or denominator is inferred from this check.

Media-bound callback retirement also prevents old chapter, preview, heatmap and
seek success receipts after a backend or load-generation replacement. Relative
keyboard transport may still control the current media, but must not update the
original media's progress/feature owner. The local load generation is not sent as
an event dimension. The normal app launch creates a new player owner per media;
the replacement matrix exercises additional stale-input boundaries. Stored
readback coverage is unchanged and no broader telemetry completion is claimed.

## Import lifecycle consent and stored outcomes

Library import binds the existing operation observer before inspection starts.
The request and later completion, failure or window-close cancellation belong to
that original consent/session. A later opt-in or revoke/regrant cannot adopt the
earlier operation. Unavailable consent or observation failures leave inspection
and durable history effects unchanged. No new event schema or transport is added.

The actual producer fixtures exercise successful temporary history commits,
failed writes and cancellation with allowed, denied, late-granted, revoked/regranted
and failed-observer contexts. Allowed payloads are retained by the real offline
outbox, serialized publicly, then authenticated and read back from local D1.
Duplicate delivery must retain one stored event per event identity.

~~~sql
SELECT action,
       COUNT(DISTINCT json_extract(dimensions, '$.operation_id')) AS operations
FROM product_events
WHERE feature = 'library_import_operation'
  AND platform = :platform AND app_version = :version
  AND occurred_at >= :since AND occurred_at < :until
GROUP BY action;
~~~

The denominator is observed valid import selections, not guaranteed worker admission or all file-picker
opens, abandoned pickers, invalid oversized selections or consent-disabled use.
A requested event with no terminal event remains unresolved; do not infer success.
A failed terminal can include partial commits; use committed_count and failed_count.
Cancellation without those counts does not mean zero files committed. The current
event does not identify the failing inspection/write stage, and this bounded
qualification does not close full import progress, native dialog or package
coverage. No filenames, paths, titles or raw errors are transmitted.


### File-action consent lifetime and stored outcomes

File-action preview binds the existing operation observer once, when its dialog
opens. Confirmation, completion, needs-attention, cancellation and recovery in
that dialog retain the same consent/session boundary. A late opt-in or a
revoke/regrant cannot adopt an earlier operation. Binding or recording failure
leaves the user's file/history action unchanged.

The actual producer regression follows preview and confirmation, commits removal
of an already-missing entry to temporary history, and separately exercises a
worker-error result and cancellation. It uses the real offline outbox with
allowed, denied, late-granted, regranted and failed-observer contexts. Initial
fixture failures caused by an omitted stable recorded-at field are retained as
test errors; the corrected prior-source matrix exposed nine consent/binding
failures. No real user files or system Trash are involved in these fixtures.

The emitted allowed payloads are exported with VODFORGE_FILE_ACTION_FIXTURE_DIR
from tests/test_library_file_actions.py and replayed by the existing enrolled
backend suite from test/fixtures/file-action-producer-events.json. Authentication,
exact stored dimensions, private-field rejection and duplicate delivery are
checked independently.

~~~sql
SELECT action,
       COUNT(DISTINCT json_extract(dimensions, '$.operation_id')) AS operations
FROM product_events
WHERE feature = 'library_file_operation'
  AND platform = :platform AND app_version = :version
  AND occurred_at >= :since AND occurred_at < :until
GROUP BY action;
~~~

The denominator is observed consenting dialog operations. It excludes rejected
admission, abandoned destination pickers, disabled consent and lost delivery.
Started marks entry into the commit path; worker submission can still refuse,
so it proves neither admitted work nor changed files. Completed must
be interpreted with committed/skipped counts, and needs_attention is not a
confirmed failed file effect. Recovery can produce further starts under the same
dialog operation. Missing outcomes remain unresolved. This bounded fixture
does not qualify all move/delete/recovery effects, native consent changes,
Windows, packaged builds or deployed ingestion.


File-action events now use the existing bounded stage dimension: analysis means
the selected files are being inspected; commit means the dialog has entered the
commit path. Preview errors and timeouts emit needs_attention at analysis, so
they no longer disappear between requested and confirmation. Completion/error
events from commit use commit, and cancellation retains the dialog's current
stage. A timeout callback after dialog destruction does not report a new outcome.

The expanded producer fixture includes inspection-error and timeout paths; neither
starts file effects or changes temporary history. Stored-query checks distinguish
two inspection operations needing attention from one commit operation needing
attention, despite delivery retries. Group by stage and action with the same
explicit platform/version/time scope. Legacy events without stage remain unknown.
The stage identifies the boundary, not the underlying drive/network error, and
does not measure latency. Busy admission, abandoned pickers and exact-package
delivery still require separate qualification.


### Import worker admission refusal

A valid file selection can reach a worker that no longer accepts requests.
The import owner checks the submit result: refusal retires the close callback,
starts no result polling and reports a friendly retry status without file or
history changes. The existing bound operation records failed at analysis with
zero committed files and the selected count failed, subject to consent.
This stage does not identify an underlying storage error. Legacy terminal
events without stage remain unknown; requested alone is not worker admission.

The producer regression closes the real ArchiveWorkOwner while the picker is
open and checks both allowed and denied telemetry. This is a controlled lifecycle
race, not evidence that an ordinary picker always triggers it. It qualifies the
refused-submission boundary only; accepted jobs, native picker interaction,
latency, and exact-package delivery require their own evidence.


## Saved-folder check consent and outcomes

The location request binds the existing operation observer before submitting its
filesystem check. Completion, missing-folder failure, timeout and cancellation
keep that original consent/session. A later grant or revoke/regrant cannot adopt
the pending result, and unavailable observation cannot bypass the binding.
The directory check and its correctly scoped UI result are unchanged by telemetry.

The producer matrix invokes the real directory-check callback on temporary paths
and the actual completion/timeout/cancel callbacks across six consent/observer
contexts. Allowed payloads travel through the real offline outbox into authenticated
local D1 tests, exact readback, private-path rejection and duplicate-safe queries.
The UI ownership suite separately covers check/open and selection replacement.
This does not establish native folder opening, Windows storage or deployed delivery.

~~~sql
SELECT action,
       COUNT(DISTINCT json_extract(dimensions, '$.operation_id')) AS operations
FROM product_events
WHERE feature = 'archive_location_operation'
  AND json_extract(dimensions, '$.location_action') = 'check'
  AND platform = :platform AND app_version = :version
  AND occurred_at >= :since AND occurred_at < :until
GROUP BY action;
~~~

The denominator is observed admitted checks, not all saved folders, denied-consent
use, busy refusals or successful media playback. Requested has no guaranteed
terminal delivery; missing outcomes stay unresolved. Available means the folder
exists, not that every file is present or playable. Timing measures worker work
where supplied, not total UI or storage latency. Timeout and cancellation callbacks
do not prove a blocked OS call has physically stopped.


## Relink review cancellation consent

Relink binds its existing operation observer when a valid saved-file selection
creates the review. That bound key travels through verification, confirmation,
cancellation and commit callbacks. Regrant cannot attach later observations to a
review created under a different consent/session, and binding failure suppresses
observations without changing review or file authority.

The maintained native regression currently qualifies cancellation while verification
is held pending: it opens the real review, presses and releases its Back to Library
button, and checks callback retirement and unchanged temporary history. Before,
pressed and returned-view captures are retained for each consent/observer context.
Input is generated through Tk, not a physical device or OS-injected pointer.
Three genuine prior-source consent failures are retained. Preview fixture mistakes
are identified separately from those failures.

The allowed native producer's real offline payloads pass authenticated local D1
storage, exact readback, private-path rejection and duplicate-safe correlation:
two events, one operation. This does not qualify verified-file results, actual
relink commits, native file pickers, full accessibility, Windows or deployed delivery.
Requested describes the admitted review; cancelled here describes leaving it
before commit, not cancelling a filesystem change already in progress.

Relink navigation now preserves the existing commit observer and its completion
callback. Library/Watch and scoped Escape use the same cancellation owner:
cancel_requested records intent, while cancelled or committed follows the actual
storage boundary. A requested cancellation is not evidence that a save was
prevented. The separate native navigation fixture proves worker/history authority;
the consent fixture remains the real offline observer and backend-readback proof.
No additional event schema or transport is introduced by this navigation repair.

### Relink worker admission and cancellation before execution

A commit_requested event describes the user's update intent, not worker admission.
If the real worker refuses submission, the same bound operation emits failed with
archive_result=unavailable. If an admitted request is cancelled or times out before
the worker invokes its function, the UI completion callback emits cancelled or
timed_out from that acknowledged result. Executed work still owns its existing
terminal observation; the callback must not duplicate it. Cancel_requested alone
does not establish cancellation or rule out an already completed save.

tests/test_relink_admission_native.py checks all three boundaries across allowed,
denied, late-granted, regranted, unavailable and failing observation. It uses the
real closed/queued worker and temporary offline ProductTelemetryOwner, retains
before/during/after captures and compares unchanged history bytes and UI records.
Timeout uses the existing poller's expired deadline, not an injected result.
Allowed producer-events.json files feed local authenticated backend readback and
replay checks. No live analytics transport or new schema is required.

Relink's bound observer retires when verification or an update reaches its final
failure, timeout, stale or cancellation result. The review widget may remain
visible for recovery; Back to Library closes that presentation without inventing
another cancelled outcome. The native fixture now follows all six failure/
cancellation boundaries through the actual return button. Verification failures
timeouts and refused starts use eighteen additional consent/observer contexts; delayed results
after timeout must not revive the review. The local backend fixture contains
twenty actual events for six operations after return and exact replay.

A refused verification submission uses the same failure settlement as a worker error:
rows and headline leave the pending state, Update stays disabled, history remains
unchanged, and the bound operation emits failed/unavailable exactly once. No worker
was admitted in this case; the during capture records an immediate outcome, not
an invented pending interval. Later return closes only the presentation.

Matte rendering reuses appearance/changed with the existing bounded theme dimension.
It does not introduce media identifiers, custom hex values or per-frame events.
The native theme matrix observes actual production-owner change emission; static
artwork changes need no additional telemetry action. Consent/wire delivery remain
separately qualified by the telemetry journey gate.
