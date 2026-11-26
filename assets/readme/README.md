# Public README screenshots

`current-design/` holds the screenshots the main README shows. They are unmodified
native window captures of the Qt Quick app on macOS, not generated mockups, made
with a fictional nature library (generated artwork and illustrative links and
activity) in an isolated profile with telemetry off. No personal media or paths
appear. `current-design/manifest.json` records each file's hash, capture date and
source commit.

They were captured on 2026-09-29 from `0ea952f`, before the native macOS toolbar
(0.2.6), so the header in them differs from current Macs. Windows shares the
application controls but has its own title bar and font rendering. The README
note that the public release may differ from main stays with them.

To replace a screenshot: capture the real app window (no desktop or browser
edges) from an isolated profile with sample media and telemetry off
(`VODFORGE_DISABLE_TELEMETRY=1`), keep native resolution, check for personal
paths, private media, clipping or stale controls, and update the manifest's hash,
date and source commit.

`forge.png` and `library.png` in this folder are captures of the former Tk
interface (September 2026), kept only because older evidence records their
hashes. The script that made them, `scripts/focus_ui_preview.py`, was removed
with the Tk interface.
