# Qt Quick port in progress

The resize experiment has become an isolated application port under
`yt_downloader/qt_quick`. The release entrypoint remains Tk while this port is
qualified. Qt now uses the shared `DownloadWorkerCore` for real downloads,
durable queue/recovery, and history writes; Library reads that history with
the existing search/type projection; Watch
uses Qt Multimedia; Activity shows in-session and recovered run status. Basic
output, quality, and mode preferences use the existing settings store. The
existing local MP3 plus still-image transaction owner also feeds Qt and Library.

This is not a replacement application or release candidate. Forge's remaining
options, Library management, complete Watch behavior,
analytics consent and telemetry, updater/repair, signed packaging, installed
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
- Mac local conversion: a real 6-second fixture MP3 and still image created a
  validated 720p MP4; a second run through the Qt bridge committed the output
  into durable Library history. The shared-control QML dialog was rendered
  and inspected. Library filter/Play source-index regression passes.
- Genesis exact `86ef55c`: QA-only source and fixture hashes verified, real
  MP4 worker/Library/ffprobe proof passed, offscreen Qt Multimedia advanced,
  and physical Forge/Options/Library/Watch screens were inspected. The first
  interactive Watch attempt failed because the elevated QA fixture file lacked
  interactive `coop` read access. Granting that one QA file read permission
  and restarting the exact QA app produced physical playback at 1/6 seconds.
  Newer source changes still require Genesis qualification.
- Existing Tk/worker/recovery tests passed after extracting the shared worker:
  366 focused, then 3529 full-suite passing with 814 platform skips.
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
