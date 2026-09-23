# Qt Quick port in progress

The resize experiment has become an isolated application port under
`yt_downloader/qt_quick`. The release entrypoint remains Tk while this port is
qualified. Qt now uses the shared `DownloadWorkerCore` for real downloads,
durable queue/recovery, and history writes; Library reads that history with
the existing search/type projection; Watch
uses Qt Multimedia; Activity shows in-session and recovered run status. Basic
output, quality, and mode preferences use the existing settings store. The
existing local MP3 plus still-image transaction owner also feeds Qt and Library.
The first six MP4 output presets and the persisted MP4 sidecar/encoder/playlist
choices now enter the same durable `DownloadJob` fields as Tk. Manual Override
and MP3 output settings use shared Tk/Qt validation in `export_inputs.py` and
enter the existing durable job fields. Their editors use `StoneButton` and
`StoneField`; invalid inputs block submission.
URL-list parsing now lives in one UI-independent owner used by Tk and Qt. Qt's
Forge list selector passes the ordered URLs and batch flag to the existing
serialized worker; a completed two-URL legal fixture created two distinct
durable Library records. The initial trial exposed that the Qt history adapter
accepted only the parent job object while the existing batch worker emits
copied child jobs. The adapter now accepts only a child with the active run ID,
listed source URL, output type and directory; a stale child regression rejects
unrelated run IDs.
The existing YouTube access choice is now shared through `cookie_inputs.py`.
Qt exposes Public, Browser, and cookies.txt as session-only choices, passes only
the selected source into `DownloadJob`, and applies the existing Windows
Chromium warning. The file path is not saved in user settings. Browser/file
access has job-field and validation proof, but account-gated live download
qualification remains open.
The custom MP3 cover validator now lives with shared `export_inputs.py`; Tk
re-exports the same function and Qt imports it directly. This removes a
widget-module dependency from that validation path while retaining the same
size, pixel, and image-decoding limits.
Qt Library now projects the existing private `LibraryAnnotationsOwner` over
completed history for search and category filtering. The Organize dialog edits
notes, tags, and category through shared stone controls, preserving any separate
description and refusing to overwrite a malformed annotation ledger. A fresh
Bridge reload proves the saved values survive restart without modifying provider
history metadata. The Qt view now asks the existing `LibraryProjectionOwner` for
completed, active, queued, and retained terminal rows. It retains the original
history index only for playable saved media; live and terminal rows can be
organized without pretending to have a local file. Archive file operations
and other Library actions still need porting.

Qt now presents analytics permission through the existing consent owner and
uses the existing product telemetry outbox. Run starts, queueing, terminal
outcomes, local conversions, first playback, settings snapshots, and worker
exports are wired through those owners. A disabled source build creates no
consent/outbox state. Focused cross-owner tests and the full repository suite
pass; packaged preview-D1, denial/off, and actual production-policy proofs
remain open. The Qt adapter is still a presentation path, with no second
consent or outbox authority.

The Qt Library now resolves Play, Open folder, and Copy path through the
current saved-item owner at click time. A stale row cannot redirect Play or
copy another item's location. Forge exposes the existing worker's Stop, Skip
item, and Skip source requests; each interrupts only this process's owned
children as in the Tk path. Activity can remove a queued run only after the
existing recovery owner durably saves the new queue. Focused tests cover stale
identity, worker signal handoff, durable queue removal, and retained queue
execution order. Move/Trash and terminal Retry remain to be ported.

This is not a replacement application or release candidate. Forge's remaining
options, Library management, complete Watch behavior,
packaged analytics delivery, updater/repair, signed packaging, installed
journeys, accessibility, and both-platform visual gates remain open.

## Rendering ownership

- `yt_downloader/qt_quick/main.py` exposes the existing `ui_chrome.action_button_image`,
  `field_border_image`, `ui_materials.backdrop_pixels`, theme, and
  `ui_button_contract.button_metrics` through one Qt adapter.
- `StoneButton.qml` owns all button labels, icons, sizes, focus, pointer input,
  and material states in this slice. Navigation and popup options instantiate
  that same control. The Watch controls pass the shared control's static-material
  option, retaining their filled stone surface without a transient hover/press
  background. Each material image is rendered at its allocated size;
  there is no nine-slice stretch of a nonstretchable surface.
- `StoneField.qml` owns the shared recessed field surface. Qt Quick lays out
  and composites the view; backdrop artwork uses `PreserveAspectCrop` to stay
  full cover while the window changes size.

This is a simpler **view rendering path** than the current Tk combination of
material generation, PhotoImage, ttk element/layout, labels, canvas projection,
and per-view geometry reconciliation. The shared worker has a separate
non-widget class; the remaining product owners still need port qualification.

## Current source-native proof

- Mac local legal fixture: MP4 and MP3 completed through Qt's runtime adapter;
  MP4 decoded with ffprobe, history reloaded after restart, and no `.vfstage`
  remained.
- Mac slow fixture: Stop retained a durable Stopped attempt, the queued MP3
  then completed, and only that valid output entered Library.
- Mac Qt Multimedia loaded the committed MP4 with a 6037 ms duration and
  reached 2800 ms playback position without a provider error in offscreen QA.
- Watch now uses the existing `PlaybackProgressOwner` and
  `PlaybackProgressBinding`. A real Qt Multimedia replay wrote the observed
  2.166/6.037-second position to the private ledger; a fresh Qt process issued
  one resume seek and reached 3.233 seconds without a provider error. The
  filtered Library Play projection and durable resume have focused tests.
- Mac local conversion: a real 6-second fixture MP3 and still image created a
  validated 720p MP4; a second run through the Qt bridge committed the output
  into durable Library history. The shared-control QML dialog was rendered
  and inspected. Library filter/Play source-index regression passes.
- Mac legal source fixture: Quality-mode Manual MP4 and nondefault 256 kbps,
  mono MP3 jobs each completed through the Qt runtime with one valid output.
  Shared Tk/Qt export-input regressions passed; the Manual and MP3 QML editors
  were rendered and inspected in isolated profile screenshots.
- Genesis exact `86ef55c`: QA-only source and fixture hashes verified, real
  MP4 worker/Library/ffprobe proof passed, offscreen Qt Multimedia advanced,
  and physical Forge/Options/Library/Watch screens were inspected. The first
  interactive Watch attempt failed because the elevated QA fixture file lacked
  interactive `coop` read access. Granting that one QA file read permission
  and restarting the exact QA app produced physical playback at 1/6 seconds.
  Newer source changes still require Genesis qualification.
- Existing Tk/worker/recovery tests passed after extracting the shared worker:
  366 focused, then 3529 full-suite passing with 814 platform skips.
- Exact `96d256f` Mac ad hoc Qt bundle passed its runtime smoke, deep code-sign
  check, and 3540 repository tests with 813 skips. Genesis received a
  SHA256-verified archive of the same commit, built a Qt executable, and its
  packaged offscreen runtime smoke exited 0. The first Windows build wrapper
  failed on PyInstaller informational stderr; its failed log is retained and
  the corrected wrapper built successfully. These packages remain diagnostic
  and predate the telemetry adapter changes. No installed visual journey or
  release-signing proof follows from them.
- After Qt telemetry wiring, 3546 repository tests passed with 813 skips on
  Mac. This is source proof for the current dirty checkout, not a package.
- The functional journeys above are source-native checks. Full packaged,
  installed, and visual acceptance for this new port remain open.

An opt-in `VODFORGE_UI=qt` package path now builds an ad hoc signed Mac Qt app
without changing the production Tk entrypoint. The first Mac candidate passed
the packaged `--runtime-smoke`, deep code-sign verification, and an isolated
profile launch with a visibly correct physical Forge screen. Its build revision
was `unknown` because the source had uncommitted package-path changes; it is
diagnostic evidence only, not an exact-commit release candidate. The
`--collect-all PySide6` trial failed signing because it included Qt Assistant's
symlink loop; explicit Qt Multimedia/Controls imports and PyInstaller's Qt QML
hook resolved that. The ad hoc bundle is about 777 MB, so dependency trimming
and exact-source candidate packaging remain open. Windows packaged QA is open.

## Native observations

The maintained pointer oracle requires two held native drags, at least 30
sound samples and 80 px of pointer/window travel each, p95 pointer-to-edge
lag <=24 px, and <=24 px pointer travel while an edge is stationary. The
Windows fixed-interior server-pixel oracle requires at least four in-flight
window sizes and no more than 2% stale pixels at 200 ms within sampled
same-size epochs. These thresholds were not changed.

| Source-native run | Observation |
| --- | --- |
| Mac ordinary right-edge resize, r3 | Passed; 3/3 px p95, 3/3 px plateau. |
| Genesis ordinary right-edge resize, r9 | Passed; 4/4 px p95, 4/4 px plateau. Sampled pixel epochs passed with no >2% lagging interior. |
| Genesis rapid bottom-right corner, r10 | Passed; horizontal p95 16/9 px, vertical p95 11/6 px, fixed opposite edges. |
| Genesis exact `688eb56` corner repeat | **Failed** the unchanged gate: horizontal p95 16/16 px, but one stationary-edge plateau reached 30 px. Opposite edges stayed fixed. |
| Genesis exact `5c4368a` corner and on-screen capture | **Failed** again on a 30 px horizontal plateau; the settled on-screen view and full-cover artwork were intact. |
| Genesis plain Qt window, same rapid path | Passed; horizontal p95 15/14 px and plateau 8/15 px. |
| Mac rapid bottom-right corner, r1/r2 | **Failed** the unchanged 24 px tracking gate. First horizontal plateau 29/37 px; second run first horizontal p95 36 px. Opposite edges remained fixed and settled UI stayed together. |
| Mac exact `5c4368a` corner | **Failed** again on a 30 px first-drag horizontal p95; opposite edges stayed fixed. |
| Mac plain Qt window, same rapid corner path | **Failed** the same gate; horizontal p95 30/23 px and plateau 29/30 px. This isolates a native window/trajectory floor of similar magnitude in one baseline run. |

The corner stress moves 220 px horizontally and 150 px vertically inward and
outward twice during each held drag, issuing 120 moves/s. One asynchronous
field-image loading trial also failed Mac; it was reverted. The plain Qt
baseline has no VODForge material or controls, so its similar failure does not
establish that the Forge renderer caused the extreme lag. The first Windows
drag attempt made during user mouse movement is retained as contaminated and
excluded from acceptance. The Windows pixel run uses four 350 ms holds during
otherwise normal native drags so the separate screen recorder can capture
same-size epochs; this does not measure 120 moves/s corner pixels. Captures
are owned-window server pixels, not physical display refresh. All results are
source-native, not signed, packaged, or installed-app evidence.

The Windows window-only capture after the exact corner repeat contained a
black lower/right region; a plain Qt window's window-only capture showed the
same region. The `5c4368a` rerun recorded an independent on-screen region:
the VODForge view and full-cover artwork were intact after the rapid drag.
The black region belongs to the window-only capture path, so that image must
not be used as the visual oracle. The failed 30 px pointer plateau lasted
31 ms in three sound samples; the left and top edges stayed fixed.

Local evidence is under ignored `build/qt-quick-native-*` and
`build/qt-quick-genesis-*`. The Genesis QA scope is `E:\VODForgeQA` only.

## Reproduce

Install PySide6, Pillow, and psutil into an isolated Python environment and
run from the repository root:

```sh
build/qt-quick-prototype-venv/bin/python engineering-quality/prototypes/qt_quick/resize_probe.py \
  --qt-python build/qt-quick-prototype-venv/bin/python \
  --output build/qt-quick-example
```

Use `--corner-stress` for the rapid diagonal trajectory. The Windows
ordinary run uses `--pixel-capture` in an interactive, unlocked session.

## Decision boundary

The ordinary resize and Windows pixel results supported starting the Qt Quick
port. The added Mac extreme-corner test fails even on a plain Qt window, and
the Windows Forge result is intermittent; the threshold was not weakened.
Promotion of the Qt entrypoint remains conditional on functional, accessibility,
signed-package, installed-app, and release journeys on both platforms. No
current release claim follows from this work.
