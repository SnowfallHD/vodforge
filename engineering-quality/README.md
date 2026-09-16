# VODForge engineering-quality harness

Encoder quality, size and speed calibration lives in the companion
[fine-tuning harness](../fine-tuning/README.md). Its measurements select settings;
this harness verifies production behavior. Set `VODFORGE_NVENC_TESTS=1` on a
supported NVIDIA Windows host to include the real preset worker GPU tests.
A skipped GPU test is not hardware verification.

## When and how to strengthen the harness

Every confirmed product bug is an input to harness improvement, whether discovered
by a user, telemetry, support, development, or a release run. Do this as part of the
same fix, before describing that work as complete. A specific regression test and
a harness improvement serve different purposes; one is not a substitute for the other.

1. Preserve the concrete reproducer and add a regression for the reported failure.
2. Identify the invariant that failed, independently of the affected screen or tool.
   Examples: accepted intent survives delayed readiness; only the current owner may
   commit a result; failed effects never report success; retries preserve identity;
   cancellation/consent withdrawal stops future effects; teardown cannot deadlock.
3. Review where that same invariant applies across existing subsystems. Select a
   bounded, risk-based set of representative owners rather than auditing the whole
   application. For lifecycle/sequencing bugs, consider player/provider readiness,
   settings persistence, queued work, telemetry transport, updater handoff, and
   asynchronous UI results—not just another control in the original screen.
4. Extend existing scenarios with meaningful variations: ordering, delayed readiness,
   failed-then-successful effects, repeated commands, owner replacement, stale/late
   callbacks, shutdown, restart, and permission changes. Choose only variations that
   apply to the owner's contract. Do not invent behavior for an unsupported operation.
5. Assert independent observable outcomes: provider state, durable files, identity,
   delivery receipts, or absence of external effects. A displayed value or successful
   method return alone is insufficient. Exercise production owners with controlled
   faults; avoid testing only a parallel toy implementation.
6. Verify the exact regression fails before the fix when feasible. Demonstrate that
   the generalized checks detect the broken invariant using the prior implementation
   or a bounded fault/mutation, then pass with the fix. Record any unexecuted tier.
7. In the fix's evidence/continuity record, identify the root cause, invariant, affected
   owners, added or reused scenarios, variations, executed results, and remaining
   coverage limits. If existing harness coverage already exercises the class, name
   that coverage and explain why it missed this instance; update its fixture, gate,
   or execution requirements as appropriate. Never say “covered” solely because a
   new regression lives under pytest.

Apply this process when a bug exposes a coverage gap, a new lifecycle/provider
boundary is introduced, or a supported behavior changes. Preserve the bounded
review budget: extend the relevant class, do not automatically rerun every E2E
journey or build a generalized runtime framework. Final publication still follows
its existing exact-artifact release requirements. Previously passed evidence does
not prove newly changed behavior.

Current cross-owner sequencing coverage is in
`tests/test_cross_owner_lifecycle.py` and `tests/test_playback_control_lifecycle.py`
(relative to this directory). The required repository suite runs these through
`pytest_harness`. They vary debounce/write failures, delivery retries/withdrawal,
readiness delays, replacement/replay, latest intent, and callback lock ordering.
The packaged playback probe additionally verifies actual provider volume after
pre-play changes and file switches. These are representative checks, not a claim
that every subsystem or possible interleaving is covered.


## Forge geometry must not replay data projection (2026-09-16)

The native unprofiled Forge5000 comparison still had a491ms maximum heartbeat
gap after the earlier selected-view fix (baseline760ms). Forge rebuilt persisted
run history both for its header and for capacity changes. The renderer's existing
snapshot no-op check came after that expensive work. Geometry now reuses its last
data projection and summary; ordinary data/progress refreshes replace it, and
forced view entry reacquires current history. Only four display candidates plus full-history summary/count are retained.
No list-identity invalidation, additional polling timer, or new data owner is introduced.

The broader invariant is that presentation-only changes must not replay data work,
while actual state transitions must remain authoritative. The25/5000record
state-authority regression failed before the fix: one initial render plus three
capacity changes made four projections. It now makes one. The same production
renderer checks queue promotion, active57percent progress, completion, and removal,
including mutation of the same list/record. Existing Library phase reconciliation,
padding burst/latest intent and RunDeck active progress tests provide the bounded
cross-owner comparisons; all132state-authority tests pass. Earlier renderer tests
asserted widget rebuild counts, so they missed work before the no-op decision.

The required native surface suite now varies empty/25/5000history, real root/deck
geometry, hidden-history mutation, re-entry, and removal-to-empty; it asserts
visible tile text, mapped geometry and capacity. Windows source-native execution passed all seven focused cases. Unprofiled
measurement on sourcef7 recorded5000row max100ms versus7c948ms;25rows108ms,
empty43ms. All four runs subsequently hit the existing thumbnail destruction
callback fault, so these are pre-shutdown measurements, not clean completion.
Full raw geometry/gap/CPU traces remain in build/variant-help-20260916/native-forge-f7af1a8.
CPU remained high (large9.875s before versus10.56s after per12s drag). Programmatic Tk geometry,
headless owner tests, source native drags and exact-package acceptance remain
separate evidence; no CPU-efficiency or Chrome-equivalence claim follows from
projection counts. Active job event frequency and very large-history projection
on actual model changes remain outside this geometry-only optimization.


### Thumbnail teardown and measurement lifetime

The native resize runs exposed a Configure callback accessing an already-destroyed
sibling thumbnail label. Python widget existence did not imply a live Tcl command.
The production thumbnail owner now rejects a closing application or missing Tcl
surfaces before image work. The prior source owner fails both closing and removed
sibling variations with TclError; current source passes. The required native test
removes the sibling, generates the bound Configure event, and exercises the normal
application close protocol, checking no callback errors and actual window exit.

The broader closed-owner invariant already appears in choice popover anchor
destruction and delayed player/telemetry callbacks. Those tests did not cover
Configure delivery during recursive sibling destruction. New coverage extends
that concrete lifecycle boundary without changing the renderer or shutdown owner.
Separately, the probe's error callback recursively called destroy and amplified
the product error into an access violation. It now exits the loop without recursive
destruction; normal completion uses the application's existing close authority,
and the final receipt is written after shutdown with all late callback errors.
An intermediate measurement file is explicitly not a clean-completion receipt.
Fresh native execution of the new guard/probe is pending; no old receipt is relabeled.

## Native control lifecycle gate

`unit_static.native_surface_contract` runs the opt-in source-native control suite
with a real Tk display. NORMAL/DEEP release evaluation requires this scenario.
Missing, empty, skipped, or failing native evidence is not a pass. Coverage includes
outside clicks (including targets that stop event propagation), Escape, owner/anchor
unmapping, window focus transfer, repeated cleanup, field chrome coverage and
Canvas/ttk field-image parity. These checks complement, not replace, packaged
Mac/Windows interaction evidence and actual cross-application switching.

The earlier choice-control audit excluded `tk.Menu` command/context menus and
checked selection rather than dismissal lifetime. Native command menus remain
intentional separate controls, not migrated choice fields. Do not describe that
inventory as all menus. Standard fields share `ui_chrome.field_border_image`;
adapters retain native editing/layout mechanics, not separate border designs.

This directory is an isolated adversarial test system for answering a bounded question with receipts:

> Is VODForge actually well engineered, performant, reliable, secure, and maintainable under the scenarios we executed?

The harness is intentionally not another downloader. Its high-volume integration layer constructs a real production `DownloadJob` and calls the existing `DownloaderApp._download_worker_single` seam without constructing Tk. From that point onward VODForge performs its own yt-dlp preflight/download, export planning, `.vfstage` ownership, FFmpeg post-processing/transcode, ffprobe validation, atomic final commit, metadata/thumbnail sidecars, and worker events.

## Evidence tiers

Every scenario has one of three non-interchangeable evidence tiers:

1. `unit_static` — existing/unit/property tests plus direct production-helper contracts, lint, type, security, dependency, dead-code, complexity, mutation, and change-surface signals. These scenarios do not claim to execute the complete worker.
2. `headless_production_pipeline` — real VODForge worker orchestration with real yt-dlp, FFmpeg, ffprobe, files, local HTTP faults, and process/resource measurement, but no Tk UI.
3. `packaged_app_e2e` — an exact packaged artifact driven through its visible UI, real worker, yt-dlp/FFmpeg, final media, shutdown/restart behavior, and independent artifact/output receipts.

A headless pass is never reported as full-application proof. If the packaged tier did not run, the report says `skipped` and leaves UI/settings/queue/lifecycle integration unproven.

### Analytics permission journeys

The repository suite covers bounded region retries, late response rejection,
one-shot browser opening, durable refusal and permission-dependent telemetry.
The `unit_static.telemetry_local_contract` scenario explicitly tests unknown and
denied permission before granting permission and exercising real Python HTTP
serialization against the loopback Worker/D1. No claim receipt substitutes for
analytics permission.

Run real Tk event-loop timing checks separately with:

```sh
VODFORGE_DISABLE_TELEMETRY=1 VODFORGE_NATIVE_UI_TESTS=1 PYTHONPATH=. \
  .venv/bin/pytest -q -s tests/test_analytics_native_journey.py
```

These intercept region responses, browser opening and claim transport. They
measure the source owner's browser-request/prompt timing, not OS browser focus.

For browser regression QA, start the companion site on loopback port 4321 and
execute `quality_harness/analytics_browser_journey.js` through Playwright's
`browser_run_code` filename input. It uses isolated browser contexts and
intercepts every API and external HTTPS request, covering browser consent,
GPC, closed tabs, source persistence, separate profiles, transient errors,
claim expiry and the final ten seconds of the permission window. Boundary
tests use the browser's virtual clock. This is an explicit manual browser
regression step, not an automatic NORMAL or packaged-app pass. A real-clock
two-minute run and OS/default-browser behavior require separate receipts.

### Original audio verification

With the harness dependencies installed and `ffmpeg` / `ffprobe` on `PATH`, run:

```sh
PYTHONPATH=.:engineering-quality .venv/bin/python scripts/verify_original_audio.py
```

On Windows, set `$env:PYTHONPATH = ".;engineering-quality"` and use
`.venv\Scripts\python.exe scripts\verify_original_audio.py`.

This networked probe downloads a single public test video through the production
worker with telemetry disabled and isolated persistence. Controlled source-family
filters exercise Opus and AAC availability separately; production Original audio
does not force either codec. It compares compressed packet hashes before and
after packaging, fully decodes the result, and records output counts, child
processes, and staging residue in `build/original-audio-verification/receipt.json`.
This is headless pipeline evidence, not packaged UI or playback proof. Use an
empty probe output directory for a fresh run; preserve older receipts separately.

## Setup

From a clean checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r engineering-quality/requirements.txt
```

Production dependencies remain in the repository's existing requirements files. Harness-only tools are isolated in `engineering-quality/requirements.txt`.

A complete FFmpeg installation containing both `ffmpeg` and `ffprobe` must be on `PATH` for headless runs. `imageio-ffmpeg` alone is insufficient because it does not supply the independent `ffprobe` executable. On macOS, Homebrew's `ffmpeg` package satisfies both. Verify the environment before spending time on a run:

```sh
./engineering-quality/run doctor
```

The packaged tier additionally needs an existing VODForge artifact. Use a locally built exact-checkpoint artifact or an independently checksum-verified release extraction; the harness does not silently build or download one and then treat it as the artifact under test.

## Commands

The release-facing FAST/NORMAL/DEEP commands and immutable candidate workflow are documented in [RELEASE_GATE.md](RELEASE_GATE.md).

FAST pre-commit gate:

```sh
./engineering-quality/run fast
```

Normal adversarial run (generated local corpus, real pipeline, faults, short soak, concurrency attack, security probes, repository tests, a bounded mutation campaign, and static signals):

```sh
./engineering-quality/run normal
```

Deeper run (longer fixtures/soak plus the first default-download W3C public boundary; the larger manifest remains an explicit candidate set rather than implied coverage):

```sh
./engineering-quality/run deep
```

The deep profile uses a controlled 50-job worker soak. If its post-warmup signal
persists and needs a longer observation under the same contract, run 100 jobs
explicitly:

```sh
./engineering-quality/run deep \
  --scenario lifecycle.repeated_job_soak \
  --soak-jobs 100
```

Run the 50-job form first. The 100-job option is diagnostic evidence, not a
machine-independent memory gate.

Add the W3C public-media boundary to a normal run:

```sh
./engineering-quality/run normal --include-public
```

Run one exact scenario:

```sh
./engineering-quality/run normal --scenario reliability.cancel_during_slow_download
```

The NORMAL gate includes `lifecycle.staging_transaction_transitions`. It polls
the real output root while the production worker downloads and transcodes,
records the `.vfstage` topology without reading media contents, skips an active
item, completes a fresh successor, and invokes the real Library-removal path.
The scenario requires private run directories and partial files to appear only
while owned, exact item-level terminal receipts, no idle `.vfstage` root after
skip or completion (including Finder-created `.DS_Store`), and proof that
removing an unrelated Library record cannot delete another active transaction.
Raw timestamped topology traces are retained with the ignored case artifacts.

Compare with a prior machine-readable result:

```sh
./engineering-quality/run normal --compare engineering-quality/reports/<baseline>/results.json
```

Start a full packaged-app session from a frozen candidate:

```sh
./engineering-quality/run packaged-e2e \
  --profile smoke \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json
```

That command re-hashes and freshly extracts the frozen ZIP, verifies the declared development or release policy, rejects any pre-existing VODForge process, creates isolated state paths, launches the exact executable in its own process group, and waits for the app's startup attestation before setting `driver_ready=true`. A visible UI driver performs the journey. Record each event with the versioned recorder rather than hand-editing JSON; the native window ID and owner PID must come from the observed window:

```sh
./engineering-quality/run record-e2e-event \
  --session engineering-quality/reports/<e2e-run>/session.json \
  --event app_visible \
  --screenshot /path/to/current-vodforge-window.png \
  --window-pid <attested-pid> \
  --window-owner-pid <native-owner-pid> \
  --window-id <native-window-id> \
  --window-title-token <session-window-token>
```

For a separate player or dialog window, keep the main session window arguments
and replace `--screenshot` with `--capture-window-id <actual-window-id>` and
`--capture-window-title <exact-native-title>`. The recorder verifies the separate
window belongs to the same attested process, captures that window directly, and
stores both window identities. Do not attribute a player screenshot to the main
window or substitute an image from another process.

If a UI surface cannot be reached, keep it missing and use `--allow-gap` only
when recording the next later event. The recorder adds the skipped event names
to the receipt; it never turns the gap into a pass.

Normal shutdown finalizes `e2e-result.json`. It passes only when ordered timezone-aware UI events, CoreGraphics window ownership/title receipts, screenshot existence and hashes, candidate/archive/bundle identity, real production stage diagnostics, output readability using the artifact's own bundled `ffprobe`, two clean launches, history/output hash persistence, cleanup, and process exit all agree. See [the driver protocol](runners/README.md).

Include a completed packaged receipt in a normal/deep comparison:

```sh
./engineering-quality/run normal --e2e-result engineering-quality/reports/<e2e-run>/e2e-result.json
```

## Full-app driver protocol

`packaged-e2e` writes exact paths and URLs to `session.json`. The required first journey is:

1. observe the packaged window;
2. enter the provided loopback URL in the visible URL field;
3. open and observe/change real Settings;
4. start Forge through the UI;
5. observe progress produced by the real worker;
6. observe truthful completion;
7. use `Command+2` (`Ctrl+2` on Windows/Linux) to open Library and inspect the committed item;
8. prove the known nonempty fixture Description is visibly inside the unchanged 360 px Selected Item rail, taller than the two-line-capped Tags region, and capped at the Library table's lower edge while the extreme title retains at least two measured visible lines;
9. request normal app shutdown.

Each observation is a structured event in `driver-events.json`: `app_visible`, `url_entered`, `settings_observed`, `forge_started`, `progress_observed`, `completion_observed`, `library_observed`, `library_description_observed`, `shutdown_requested`, `restart_requested`, and `restart_observed`. The recorder copies screenshots under the session's `ui/` directory, hashes them, timestamps the event, and rejects duplicates or wrong order. `library_description_observed` must include the exact visible fixture text. A private, launch-bound Tk receipt independently proves that the Description heading/body are mapped and contained, its first display line is visible, its body is taller than Tags and ends at the measured Library table edge, the rail's configured height remains the pre-existing 360 px while any responsive grid allocation is recorded separately, Tags is bounded to two requested text lines, the stress title retains at least two font-measured visible lines, and the stress title/path were ellipsized. The `control.json` action `relaunch` makes the session reopen the same exact artifact with the same isolated app data so restart/history and media hashes can be checked before the final quit.

The deeper packaged profile is first-class rather than an implied consequence of the smoke journey:

```sh
./engineering-quality/run packaged-e2e \
  --profile deep \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json
```

It additionally requires visible receipts for a throttled active run, a second run queued through the UI, cancellation requested through the UI, a clean cancelled state, the queued job advancing, and that queued job reaching completion. A smoke pass therefore proves only the happy path plus restart and does not claim queue/cancellation coverage.

The UI driver is observation/control only. It does not call production Python helpers, forge outputs, or synthesize worker events. VODForge exposes real-user view shortcuts (`Command+1/2/3` on macOS, `Ctrl+1/2/3` on Windows/Linux) through the same canonical view authority as the visible navigation. This gives native drivers a stable route when Tk children are not exposed through accessibility. Missing Library evidence still fails the tier instead of being replaced by shortcut existence or headless evidence.

### Native driver keyboard fallback

If a coordinate click only changes hover and does not invoke the control, stop
repeating it. A hover screenshot is not proof of activation or an app click defect.
Use ordinary keyboard navigation and observe the resulting window:

- With focus in the Forge URL entry, press Tab twice (format selector, then
  Settings) and Space. Verify that **VODForge Settings** actually opens before
  recording `settings_observed`. This route was observed in the signed 0.2.0
  macOS arm64 candidate; recheck focus/order for other layouts and platforms.
- Escape closes Settings. Verify the Forge window before continuing.
- Use the existing view shortcuts above for Library and Activity.

Do not assume Command-comma is implemented or use invisible callback invocation
as a substitute. Keep failed/limited runs intact; retry with new session evidence.
The keyboard Settings observation alone does not prove download, completion,
Library, or restart steps.

## Corpus policy

The tracked [manifest](corpus/manifest.json) separates generated, default-download public, external-boundary, and optional platform candidates.

- Generated fixtures come only from FFmpeg `testsrc2` and `sine` filters.
- W3C media was explicitly published for HTML media testing and is the preferred public default-download boundary.
- Blender-hosted open-movie files carry explicit Creative Commons terms.
- YouTube Creative Commons candidates separate copyright permission from platform automation authorization. They are metadata-only/download-disabled by default; a Creative Commons label alone is not treated as unconditional authorization to automate YouTube.
- Cookies, browser profiles, authenticated/private media, DRM, commercial music, and random creator uploads are out of scope.

External format IDs, exact bitrates, item counts, and hashes are not pinned unless the publisher supplies an immutable artifact. Source properties and generated-output properties are stored separately and compared from evidence captured in the same run.

## Fault and measurement model

The loopback origin injects HTTP errors, retryable failures, throttled transfer, connection interruption, metadata/thumbnail stress, Unicode, punctuation, and long titles. Other probes use controlled unwritable paths, symlinks, deliberately wrong ffprobe contracts, child failures, cancellation, repeated jobs, and simultaneous unsupported worker attacks.

The harness records:

- source-analysis/job-initialization, download/post-process, transcode, validation, commit, cleanup, and total time where available;
- progress bytes, effective throughput, CPU, process-tree RSS, child count, zombies, file descriptors, threads, output bytes, peak disk, and staging residue;
- independent ffprobe container/stream/codec/bitrate/duration evidence;
- scenario status, raw evidence paths, classified findings, and suggested fixes;
- machine, load, disk, Git SHA/dirtiness, tool versions, and optional baseline deltas.

The controlled deep soak additionally writes incremental post-GC observations
for root RSS/USS where available, traced Python allocations, GC-tracked object
types, FDs, Python and OS threads, process children, private thumbnail-cache
state, on-disk history state, isolated temp files, and staging residue. It reuses
one exact source identity and releases each full pipeline result before sampling
so harness receipts do not create a linear retention signal. Tracemalloc keeps
only baseline/final raw snapshots and bounded intermediate deltas.

This headless tier never constructs Tk or pumps UI events. Tk image counts,
in-memory Library history, and completed-run image ownership are therefore
reported as unavailable, not zero. Those require packaged/UI evidence.

Performance values are not universal pass/fail constants. Compare like-for-like machines and corpus conditions; comparison refuses metric deltas when profiles, scenario/tier sets, or explicit workload contracts differ and reports commit/machine equality separately. A soak records memory/FD trends but does not convert a single machine's arbitrary byte threshold into a leak conclusion.

## Result contract

Each run writes:

```text
engineering-quality/reports/<run-id>/
  results.json
  summary.md
```

Raw case diagnostics and media stay in ignored `engineering-quality/.runs/<run-id>/`. The JSON contract is defined in [run-result.schema.json](schemas/run-result.schema.json). Every negative finding includes an area, reproduction, evidence, severity, classification, and suggested fix. Findings use only these requested classifications:

- correctness defect
- reliability defect
- security defect
- performance defect
- maintainability risk
- code smell
- stylistic preference

Static-tool output is a signal, not proof. A security issue is reported only when a safe reproducer demonstrates the broken property and its preconditions are stated.

## Maintainability change probes

[change-probes.json](maintainability/change-probes.json) measures the current reference/test surface for adding an output mode, changing filename organization, adding metadata, altering playlist behavior, and extending the downloader backend. These probes do not pretend to be completed changes; they identify coupling and protection surfaces. Deep evolution benchmarks should apply each change in a repository-owned temporary worktree, run the full relevant gates, record actual files touched/regressions, and then remove the worktree only after clean containment verification.

## Current first-version boundaries

### Telemetry contract checks

Ownership is a cross-entry-point invariant, not an enrollment-only test. The local
contract exercises fresh, claim, cloud-seen, cloud-click, legacy-launch and waitlist
creation before enrollment. It requires authenticated retries, second-credential
rejection, exactly one durable credential, and no legacy mutation after enrollment.
An omitted matrix case fails the receipt. Harness self-tests reject green delivery
results with duplicate credentials or unauthorized writes. The site suite adds
reverse order, concurrent enrollment and revoked-credential coverage.

The gap addressed here was split fixtures: claim-first tested metadata while
exclusive ownership was tested only on a fresh row. The old loopback probe never
issued a real claim and read only version/event counts. Future identity or durable
row creators must be added to both matrices; these checks do not imply exhaustive
security verification or official-binary attestation.

NORMAL/DEEP include the sibling `vodforge-site` backend suite and a local-only
Python client → production Worker owner → ephemeral D1 contract check. Set
`VODFORGE_SITE_REPO` if the site checkout is elsewhere; it must be clean with its
Node dependencies installed. Receipts record the site commit before/after.
The contract exercises first launch, version updates, event deduplication, and
real injected HTTP failures serialized through the product-event owner. It is
source integration evidence, not deployed routing or packaged-app proof.

Headless profile runs force telemetry suppression. Public releases additionally require the [packaged preview-D1 telemetry journey](TELEMETRY_RELEASE_GATE.md) on macOS and Windows; use `packaged-e2e --profile telemetry --telemetry preview` for that separate positive gate. A harness-process audit guard
blocks production telemetry hosts and fails the isolation receipt even if a
caller swallows the exception. The local Worker denies outbound fetches and
uses only explicitly supplied local bindings/migrations; no production D1 is
accessed. Child processes inherit suppression; the Python audit hook itself
does not cover child processes. FAST also checks the isolation receipt.

The first version makes real local MP4/MP3 output, same-run source-quality selection, HTTP 404/503, connection interruption, slow transfer, download and transcode cancellation, unwritable destinations, FFmpeg dependency failure, fresh-output validation, symlink/path, URL-secret, soak, defensive simultaneous-worker attack, static/test, bounded history mutation, maintainability, and packaged happy-path/restart journeys runnable. The packaged deep protocol includes queue and cancellation but still needs a stable repository-owned native UI automation engine.

Highest-value additions are forced process-kill/restart with stale-stage accounting, low-disk volumes, real provider playlist scaling, duplicate/queue mutation through packaged UI, active-run updater shutdown, blocked-analysis slot exhaustion, multi-hour soak, actual temporary-worktree change implementations, and a wider mutation campaign.

Expanded feature telemetry is documented in
[`docs/telemetry-features.md`](../docs/telemetry-features.md). The backend gate
checks cross-language vocabulary parity, and the preview release gate checks
feature/action coverage and attempt relationships as well as event counts.
`python -m quality_harness.telemetry_feature_probe --site ../vodforge-site
--version <registered-version> --output <fresh-evidence-directory>` is an opt-in
preview serializer/D1 contract check. Supply the QA key through the environment.
It is not native UI or release proof; final artifacts must follow
[TELEMETRY_RELEASE_GATE.md](TELEMETRY_RELEASE_GATE.md).


### Pre-publication update fixture

`quality_harness.update_fixture` serves only explicitly listed final release
archives on a scoped loopback URL. The existing isolated preview mode can use
that feed for native update and Repair journeys without publishing first or
changing signed bytes. It records hashes and requests, supports a real HTTP503
fault, and preserves normal publisher verification. See the
[telemetry release gate](TELEMETRY_RELEASE_GATE.md#isolated-updater-feed-before-publication)
for the baseline, launch environment and required D1/UI evidence.

### Consent withdrawal and prospective operation evidence (2026-09-16)

The telemetry owner must not recreate an outbox after withdrawal or resume a
pre-withdrawal observation after a failed purge, restart, or rapid re-enable.
The prior owner fails test_revocation_survives_locked_outbox_and_restart_without_replay:
an independently recorded sink receives the old row after denied consent and a
locked outbox. Prior-source receipt:
build/variant-help-20260916/privacy-revocation-before.log. A private epoch in
existing consent settings/outbox now invalidates old observations; it is excluded
from the wire. Separate tests cover permission-to-write ordering, revocation
between the two sinks, immutable replay and fresh post-enable observations.
An already in-flight request cannot be unsent. Previous tests assumed successful
purging or stopped before re-enable, so they missed this cross-lifecycle defect.

Operation observations are prospective, separate from session feature presence.
The actual local converter captures failure facts before formatting display text;
controlled failures at preparation/image/transcode/validation/commit assert the
independently observed exception, final files/staging state, and persisted typed
event. Playback checks provider failure followed by actual Playing and Ended.
The source-native Windows Help runner pairs OS input, visible modal/grab receipts
and local outbox events; the injected collection policy and local sinks are
explicitly labeled, never packaged/preview proof. Its first instrumented matrix
caught missing forced-tour closure telemetry even though the tour was visible;
forced teardown now retires the existing operation owner.

The resize invariant is that hidden primary views do not consume geometry work or
history projection, while selected views restore current layout on re-entry.
The actual native view-allocation test fails on old source and passes after the
change. Profiled quiet drags reveal the expensive hidden history path; absolute
performance qualification still requires unprofiled before/after comparisons with
runtime/driver hashes, CPU intervals, commanded and delivered geometry, and no
screenshots during measurement. Empty/normal/large Library, Forge, panel/focus/
scale/teardown variations and Mac/exact signed artifacts remain distinct required
tiers. Event counts are not frame rate or Chrome parity.

Backend migration tests preserve historical columns, indexes and FKs, reject
null/non-failure action diagnostics, and exercise immutable replay through the
enrolled route. CRM tests use mixed legacy/new/source/channel fixtures,
out-of-order arrival and incomplete sequences; commits/reuse count only at their
actual observation, never again in completion summaries. These are source checks;
fresh preview D1, blinded investigation, native consent-positive and denied/off
signed artifacts, Update/Repair and full release gates remain required.

The local converter also observes the successful physical commit before later
metadata construction, using its existing worker event queue. A prior-source
case produces an independently verified file but no commit observation when
metadata then fails (local-commit-observation-before.log). The regression checks
preserved bytes, one observation, history-stage failure and cleaned staging.
Earlier conversion tests stopped at commit failures or fully successful results,
so they missed the committed-file/later-history boundary. This complements the
download sidecar-partial case; neither proof infers an absent event means zero.

Native support testing also found reply-enabled Feedback at bounded small window
sizes collapsed the message field to 17px. Existing modal layout ownership now
allocates reply-field height while retaining the parent bound. The unchanged
independent field-height/footer/backdrop checks failed twice before and all
25 native cases passed afterward. Exact packaged visual checks remain required.

### Blind packet follow-up: observations cannot interfere with work

The coordinator assessed only persisted preview-D1 events and approved context
before the fixture was revealed. It identified the failing app frame and explicit
retry, distinguished two commits from two reuse observations, and explicitly
could not establish exact trigger, sidecar cause or same-source settings history.
The locked assessment is maintained in the separate coordinator audit workspace.

The revealed malformed in-memory history row fault occurred inside the newly
added observation comparison. The normal durable loader already discards
non-mapping rows, so this injection does not establish a reachable on-disk user
failure. Observations now return unknown for absent/malformed evidence, and the
existing legacy-ownership lookup skips non-mapping rows while retaining exact
signature/path requirements. Cross-owner CPU pipeline tests deliberately carry
invalid rows through actual transcode, validation, commit, reuse and optional
sidecar failure; 35 focused cases pass. No actual media error is swallowed.

A separate independently verified bug mislabeled new variant reuse as owned
legacy by comparing a suffix with a whole path component. Namespace observations
now compare the actual validated artifact directory with the existing output
planner's target and require actual legacy-path membership otherwise. The prior
real-pipeline test fails (namespace-sidecar-before.log); the corrected cases pass
across every CPU preset. Optional artwork, metadata and thumbnail failures now
emit a bounded sidecars-stage diagnostic at both fresh and reuse boundaries,
with failed media count zero and sidecar count one; completed partial observations
remain separate. This closes a blind-investigation limit without raw messages.

The initial producer driver mistakenly tried to populate history from the
content-only metadata sidecar; it therefore retained empty history, making its
first_observed values accurate but useless for same-source claims. Follow-up
must consume actual history_record events through the existing history owner.
Never reinterpret the original packet as stronger evidence.
