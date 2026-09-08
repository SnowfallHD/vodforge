# Curated feature showcase

These are native VODForge UI captures using fictional review fixtures, not user
media or personal paths. They are bundled locally and require no network access.
The catalog and normalized crops live in `yt_downloader/whats_new.py`.

Only change `SHOWCASE_ID` when intentionally publishing a new feature showcase.
Ordinary version bumps and release-note changes must not trigger it. An empty
`HIGHLIGHTS` tuple disables it. Dismissal is stored by the existing settings owner.

Capture source: `scripts/focus_ui_preview.py --approved --public-fixture`, with
`--local-conversion`, `--annotation`, or `--player MP4`, plus `--capture PATH`.
The player capture is a process-free visual fixture, not playback evidence.

UI Updates leads the catalog with Activity (`--view activity`), Settings
(`--settings`), and a close crop of the existing Player controls. The original
three feature slides follow unchanged. These are editorial highlights, not a
complete release-note list or claims about measured playback performance.
