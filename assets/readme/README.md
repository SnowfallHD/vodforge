# Public README screenshots

Window-specific captures of the native app, not generated UI mockups. They use
fictional sample metadata/artwork and an isolated source-review session with
telemetry disabled. Progress and file sizes are illustrative, not benchmark or
real-download evidence. Paths are anonymous.

Captured on macOS; Windows shares application controls but has platform-specific
title-bar/font rendering. The public release may lag main; retain that README note.

From the repository root on macOS:

```sh
VODFORGE_DISABLE_TELEMETRY=1 PYTHONPATH=. .venv/bin/python scripts/focus_ui_preview.py --approved --public-fixture --capture assets/readme/forge.png
VODFORGE_DISABLE_TELEMETRY=1 PYTHONPATH=. .venv/bin/python scripts/focus_ui_preview.py --approved --public-fixture --view library --capture assets/readme/library.png
```

Inspect results before committing: no desktop/browser edges, personal paths,
private media, empty progress panels, clipping, or stale controls. Keep native
capture resolution; do not upscale old images to conceal poor quality.
