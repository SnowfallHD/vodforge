# VODForge application architecture

How the desktop app is put together: who owns which state, how work flows from a
pasted link to a saved file, and where the security boundaries are. For screens see
[current design](current-design.md); for UI rules see the
[component contract](ui-components.md). The Tk-era version of this document is kept
in [history](history/architecture-tk-era.md).

## Entry point and composition

`main.py` (or the equivalent `qt_main.py`) → `yt_downloader/app.py` →
`yt_downloader/qt_quick/main.py`. `app.py`
also dispatches two non-GUI commands (`--channel-artwork-worker`,
`--debug-preflight`).

`qt_quick/main.py` builds the QML engine (`create_engine`) and the `Bridge`, the one
object QML talks to. `Main.qml` lays out Forge, Library, Watch and Activity and shares
the stone controls (`StoneButton`, `StoneCheckBox`, `StoneField`, `StonePopup`,
`SceneIcon`, `ArtworkImage`). The Bridge composes existing owners. It doesn't contain
a second download pipeline, history writer or settings store.

## Who owns what

| State | Owner |
| --- | --- |
| Download execution, queue, cancel/skip | `download_service.py`, adapted for Qt by `qt_quick/runtime.py` (`DownloadRuntime`) |
| Interrupted-run recovery journal | `run_state.py`; Qt run controls in `qt_quick/run_controls.py` |
| Completed-output history (the only writer) | `history.py`, with recovery and deferred publication in `library_history.py` |
| Library rows | `library_state.py` derives them from history, active/queued runs and annotations; `qt_quick/scene_projection.py` and `library_window_model.py` present them |
| Notes, tags, categories | `library_annotations.py` |
| File move, delete and relink | `archive_file_operations.py`, `archive_relink.py`, `archive_work.py`; Qt handoff in `qt_quick/library_files.py` and `relink.py` |
| Watch catalog and playback queue | `watch_library.py`, `watch_queue.py` |
| Playback | Qt Multimedia in `PlayerScene.qml`; progress in `playback_progress.py` |
| Settings | `settings_store.py` (`settings.json`) |
| Installation identity and onboarding | `cloud_funnel.py` (`installation.json`) |
| Analytics permission | `analytics_consent.py`; telemetry delivery in `product_telemetry.py` and `telemetry_*.py` |
| Updates and Repair | `updates.py`, `update_recovery.py`; Qt handoff in `qt_quick/update_session.py` |
| Feedback and reviews | `support_payload.py`, `support_transport.py`; Qt session in `qt_quick/support.py` |
| Theme and materials | `product_theme.py`, `visual_materials.py`, `visual_chrome.py` |

Rules that keep this working:

- **Library is derived, never an authority.** Every row comes from canonical
  history and run state. Run ID is the key. Removing a Library entry changes
  VODForge's history, not media files, unless a file action is explicitly chosen.
- **Settings are next-run values.** A submitted job takes a snapshot; Forge renders
  the selected run's own settings, not today's Settings.
- **Selection is presentation.** Selecting a card never grants execution authority.
- **One render owner per surface.** QML components own their own drawing; callers
  pass data.
- **Required actions stay visible.** Dialog actions and progress live outside
  scrolling content at every supported window size.

## From link to saved file

1. Forge submits a `DownloadJob` with a snapshot of the settings.
2. The worker expands playlists, analyzes each item and builds an `ExportPlan` or
   `AudioExportPlan` from real source formats (`export_planning.py`,
   `original_audio.py`, `source_selection.py`).
3. An existing output is reused only if it passes the same checks as a fresh one.
4. yt-dlp downloads into a private per-attempt staging folder (`0700`).
5. FFmpeg transcodes or packages as the plan requires.
6. ffprobe validates the staged media against the plan (`output_validation.py`).
7. `safe_output.py` commits validated files under the chosen folder atomically. It
   rechecks containment just before writing and refuses redirecting descendants.
8. Optional sidecars are written from committed paths, then history is updated.
9. A terminal event distinguishes success, partial success, cancel, skip and failure.

yt-dlp and FFmpeg child processes are tracked and must be stopped and reaped before
shutdown counts as clean (`process_lifecycle.py`). A hard crash is recovered on the
next launch from the run journal.

## Worker-to-UI events

Background threads never touch QML objects. Workers put typed `(kind, payload)`
events (`worker_events.py`) on a queue. On the GUI thread, the Bridge's `_pump`
timer calls `DownloadRuntime.poll()`, which drains the queue in order. Events can outlive the run that produced them, so handlers
check the run ID before acting.

## Platforms

Screens and state are shared; only native integration differs. `platform_services.py`
is the dispatch boundary (folders, pickers, runtime discovery, subprocess policy).

- **macOS:** `qt_quick/mac_windowing.py` owns the window. The header is native AppKit
  toolbar items (`platforms/macos/header_items.m`, bridged by
  `qt_quick/mac_toolbar_header.py`); full-screen lifecycle is in
  `fullscreen_lifecycle.m`. Both compile into one helper dylib; see
  [the header history](history/macos-header.md) for why.
- **Windows:** `qt_quick/windows_windowing.py` and `WindowsFrame.qml` draw the frame
  while Windows keeps resize, snap and system-menu behavior. Native helpers live in
  `platforms/windows/`.

Importing one platform's code must not load the other's native libraries.

## Security and privacy boundaries

- **Updates:** an update installs only after its size, SHA-256 checksum and
  publisher identity check out (Authenticode on Windows; Developer ID, notarization
  and Gatekeeper on macOS). macOS re-verifies before swapping. These checks stay in
  `updates.py` and the release tooling; see [Releasing VODForge](release.md).
- **Telemetry:** needs both a production build policy (`telemetry_policy.py`) and
  the user's permission. Source and private builds never send. No URLs, titles,
  file names or paths are collected; see [telemetry features](telemetry-features.md).
- **Private files:** settings, history and receipts are written with private
  permissions (`private_files.py`, `private_json.py`). Malformed files are preserved
  and fail closed rather than being silently replaced.

## Testing tiers

`engineering-quality/` has three evidence tiers that don't substitute for each
other. Unit and static checks cover contracts. Headless pipeline scenarios run the
real worker. Packaged end-to-end runs drive the real app. A passing headless run
doesn't prove the packaged app works. See [the harness README](../engineering-quality/README.md)
and [the release gate](../engineering-quality/RELEASE_GATE.md).

## Repository map

| Location | Contents |
| --- | --- |
| `main.py`, `qt_main.py`, `yt_downloader/app.py` | Entry point |
| `yt_downloader/qt_quick/` | Qt Bridge, QML scenes and Qt adapters |
| `yt_downloader/` | Download, history, Library, playback, telemetry and update owners |
| `yt_downloader/platforms/` | macOS and Windows native code |
| `tests/` | Source tests; Qt tests run in separate CI partitions |
| `engineering-quality/` | Quality harness, release gate, acceptance ledger, change log |
| `fine-tuning/` | Encoder experiments behind the export presets |
| `scripts/` | Packaging and development utilities |
| `docs/` | Product, architecture and release guides ([index](README.md)) |
| `assets/` | Icons, brand art and README screenshots |
