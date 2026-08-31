# VODForge engineering-quality harness

This directory is an isolated adversarial test system for answering a bounded question with receipts:

> Is VODForge actually well engineered, performant, reliable, secure, and maintainable under the scenarios we executed?

The harness is intentionally not another downloader. Its high-volume integration layer constructs a real production `DownloadJob` and calls the existing `DownloaderApp._download_worker_single` seam without constructing Tk. From that point onward VODForge performs its own yt-dlp preflight/download, export planning, `.vfstage` ownership, FFmpeg post-processing/transcode, ffprobe validation, atomic final commit, metadata/thumbnail sidecars, and worker events.

## Evidence tiers

Every scenario has one of three non-interchangeable evidence tiers:

1. `unit_static` — existing/unit/property tests plus direct production-helper contracts, lint, type, security, dependency, dead-code, complexity, mutation, and change-surface signals. These scenarios do not claim to execute the complete worker.
2. `headless_production_pipeline` — real VODForge worker orchestration with real yt-dlp, FFmpeg, ffprobe, files, local HTTP faults, and process/resource measurement, but no Tk UI.
3. `packaged_app_e2e` — an exact packaged artifact driven through its visible UI, real worker, yt-dlp/FFmpeg, final media, shutdown/restart behavior, and independent artifact/output receipts.

A headless pass is never reported as full-application proof. If the packaged tier did not run, the report says `skipped` and leaves UI/settings/queue/lifecycle integration unproven.

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
8. prove the known nonempty fixture Description is visibly inside the unchanged 360 px Selected Item rail;
9. request normal app shutdown.

Each observation is a structured event in `driver-events.json`: `app_visible`, `url_entered`, `settings_observed`, `forge_started`, `progress_observed`, `completion_observed`, `library_observed`, `library_description_observed`, `shutdown_requested`, `restart_requested`, and `restart_observed`. The recorder copies screenshots under the session's `ui/` directory, hashes them, timestamps the event, and rejects duplicates or wrong order. `library_description_observed` must include the exact visible fixture text. A private, launch-bound Tk receipt independently proves that the Description heading/body are mapped and contained, its first display line is visible, the rail's configured height remains the pre-existing 360 px while any responsive grid allocation is recorded separately, and the stress title/path were ellipsized. The `control.json` action `relaunch` makes the session reopen the same exact artifact with the same isolated app data so restart/history and media hashes can be checked before the final quit.

The deeper packaged profile is first-class rather than an implied consequence of the smoke journey:

```sh
./engineering-quality/run packaged-e2e \
  --profile deep \
  --candidate engineering-quality/candidates/<candidate-id>/candidate-artifact.json
```

It additionally requires visible receipts for a throttled active run, a second run queued through the UI, cancellation requested through the UI, a clean cancelled state, the queued job advancing, and that queued job reaching completion. A smoke pass therefore proves only the happy path plus restart and does not claim queue/cancellation coverage.

The UI driver is observation/control only. It does not call production Python helpers, forge outputs, or synthesize worker events. VODForge exposes real-user view shortcuts (`Command+1/2/3` on macOS, `Ctrl+1/2/3` on Windows/Linux) through the same canonical view authority as the visible navigation. This gives native drivers a stable route when Tk children are not exposed through accessibility. Missing Library evidence still fails the tier instead of being replaced by shortcut existence or headless evidence.

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

The first version makes real local MP4/MP3 output, same-run source-quality selection, HTTP 404/503, connection interruption, slow transfer, download and transcode cancellation, unwritable destinations, FFmpeg dependency failure, fresh-output validation, symlink/path, URL-secret, soak, defensive simultaneous-worker attack, static/test, bounded history mutation, maintainability, and packaged happy-path/restart journeys runnable. The packaged deep protocol includes queue and cancellation but still needs a stable repository-owned native UI automation engine.

Highest-value additions are forced process-kill/restart with stale-stage accounting, low-disk volumes, real provider playlist scaling, duplicate/queue mutation through packaged UI, active-run updater shutdown, blocked-analysis slot exhaustion, multi-hour soak, actual temporary-worktree change implementations, and a wider mutation campaign.
