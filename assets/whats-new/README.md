# Curated feature showcase

These are native VODForge UI captures, not generated UI mockups. Activity is a
direct Forge capture after a real YouTube download (DMSUSyAy0qM), with telemetry
disabled and an isolated output directory. Its friendly stages are derived from
observed production worker statuses, not scripted review lines or fabricated timestamps.
The other captures use sample media and review fixtures, not user media or
personal paths. They are bundled locally and require no network access.
The catalog and normalized crops live in `yt_downloader/whats_new.py`.
`activity-mode.png` is a native component excerpt using observed statuses from
the same completed run receipt. It illustrates the mode slider and friendly
stages only, omitting technical-log context and its warning notice. The actual
app keeps warnings visible; this is a curated feature excerpt, not a complete
run-log screenshot. The faces are drawn controls, not platform emoji.
The Activity highlight intentionally crops to five observed friendly phases:
preparing, downloading, converting, validating, and successful completion. It excludes warnings,
the page heading, media title, URLs, paths, folder action, and scrollbar without
recreating or rewriting events.

Only change `SHOWCASE_ID` when intentionally publishing a new feature showcase.
Ordinary version bumps and release-note changes must not trigger it. An empty
`HIGHLIGHTS` tuple disables it. Dismissal is stored by the existing settings owner.

Capture source: `scripts/focus_ui_preview.py --approved --public-fixture`, with
`--local-conversion`, `--annotation`, or `--player MP4`, plus `--capture PATH`.
The player capture is a process-free visual fixture, not playback evidence.

UI Updates leads the catalog with real-download Forge progress, Settings
(`--settings`), and a close crop of the existing Player controls. The original
three feature slides follow unchanged. These are editorial highlights, not a
complete release-note list or claims about measured playback performance.
