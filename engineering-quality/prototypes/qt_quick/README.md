# Qt Quick Forge vertical slice

This source-native experiment tests whether Qt Quick can keep a VODForge view
together during native resize. It is not a replacement application or release
candidate. Download, Library, Watch, Activity, settings, telemetry, update,
packaging, and installed-app journeys are not connected here. The Download
action validates a URL and reports that the engine is disconnected.

## Rendering ownership

- `main.py` exposes the existing `ui_chrome.action_button_image`,
  `field_border_image`, `ui_materials.backdrop_pixels`, theme, and
  `ui_button_contract.button_metrics` through one Qt adapter.
- `StoneButton.qml` owns all button labels, icons, sizes, focus, pointer input,
  and material states in this slice. Navigation and popup options instantiate
  that same control. Each material image is rendered at its allocated size;
  there is no nine-slice stretch of a nonstretchable surface.
- `StoneField.qml` owns the shared recessed field surface. Qt Quick lays out
  and composites the view; backdrop artwork uses `PreserveAspectCrop` to stay
  full cover while the window changes size.

This is a simpler **view rendering path** than the current Tk combination of
material generation, PhotoImage, ttk element/layout, labels, canvas projection,
and per-view geometry reconciliation. The prototype does not demonstrate a
simpler complete product: controller, input, accessibility, DPI, player,
packaging, updater, and all other views still need a port and qualification.

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
| Mac rapid bottom-right corner, r1/r2 | **Failed** the unchanged 24 px tracking gate. First horizontal plateau 29/37 px; second run first horizontal p95 36 px. Opposite edges remained fixed and settled UI stayed together. |
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

Local evidence is under ignored `build/qt-quick-native-*` and
`build/qt-quick-genesis-*`. The Genesis QA scope is `E:\VODForgeQA` only.

## Reproduce

Install PySide6, Pillow, and psutil into an isolated Python environment and
run from the repository root:

```sh
.venv/bin/python engineering-quality/prototypes/qt_quick/resize_probe.py \
  --qt-python build/qt-quick-prototype-venv/bin/python \
  --output build/qt-quick-example
```

Use `--corner-stress` for the rapid diagonal trajectory. The Windows
ordinary run uses `--pixel-capture` in an interactive, unlocked session.

## Decision boundary

The ordinary resize and Windows pixel results support Qt Quick as a promising
renderer for VODForge's responsive view. The added Mac extreme-corner test
fails even on a plain Qt window and needs a separate acceptance decision for
that trajectory; its threshold was not weakened. A product port is justified
only after the real functional, accessibility, signed-package, installed-app,
and release journeys pass on both platforms. No current release claim follows
from this slice.
