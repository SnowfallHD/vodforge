# VODForge application architecture

This document describes ownership and security boundaries in the desktop application. It is intentionally about runtime contracts, not a class-by-class inventory.

## Composition and state ownership

`DownloaderApp` is the Tk composition root. It creates the views, owns application-lifetime services, and connects UI actions to one canonical `DownloadJob` execution path. View helpers may render or mutate widgets, but they do not create a second download implementation.

State is divided by authority:

- Next-run values remain application-owned Tk variables while Settings edits them. A `DownloadJob` receives an immutable-by-convention snapshot at submission.
- Active and queued execution belongs to `active_job`, `pending_jobs`, and the worker control flags.
- A run owns its preview metadata, activity lines, terminal state, and output profile. Forge renders the selected run; it does not rewrite that run from current Settings values.
- `history.py` owns the durable schema and sanitization. `download_history` is the durable completed-output ledger; `metadata_items` is an atomically replaced, immutable-derived Library snapshot and never an authority. Library removal changes VODForge presentation history, not media files, unless a separate file action is explicitly requested.
- `library_annotations.py` separately owns durable user notes, tags, and categories. Categories are user-created Library collections exposed through projection-backed filtering; they do not change provider metadata or output paths.
- `media_player.py` owns local playback state, synchronization, and its FFmpeg-family child processes. Missing-media recovery is planned by `library_media_recovery.py` from durable history and a validated saved job profile; UI code cannot reconstruct or guess an output profile.
- UI selection is presentation state. It must not become execution authority.

## UI seams

The composition root still owns the Forge and Library widget trees because their controls share selected-run and execution state. The extracted seams are narrower:

- `focus_settings.py` owns Settings dialog construction and visibility. It receives explicit variables and actions; it does not own the next-run settings values or create jobs.
- `library_state.py` owns the single Library membership/status projection from canonical run, queue, terminal, preview, history, and annotation owners. The application atomically adopts and renders that immutable snapshot; it does not append, remove, or terminalize Library rows.
- `library_search.py` owns render-only search/category predicates. `library_search_ui.py`, `media_player_ui.py`, annotation UI, and missing-media recovery UI each own rendering strategy for their local surface.
- `ui_layout.py` owns shared responsive geometry policy. `ui_widgets.py` owns reusable Tk controls and input behavior. `ui_theme.py` owns the shared visual tokens.

These modules are not independent view models. Execution authority and cross-view selection remain explicit in `DownloaderApp` so a second state system cannot drift from the real queue.

## Worker lifecycle

The worker processes a submitted source in ordered phases:

1. Expand the snapshotted source into playlist or individual-item entries.
2. Analyze one item and create an `ExportPlan` or `AudioExportPlan` from real source formats.
3. Reuse an existing output only after it passes the same plan contract as a fresh output.
4. Download into a private per-item attempt staging directory using yt-dlp.
5. Transcode or package with FFmpeg as required by the plan.
6. Validate the staged media with ffprobe against the canonical plan-matching contract.
7. Commit validated files beneath the selected output root through the secure atomic-commit boundary.
8. Write optional sidecars using committed paths only, then emit a history event. The UI-thread handler owns durable history persistence.
9. Emit a terminal outcome that distinguishes success, partial success, cancellation, skip, and failure.

Cancellation and skip requests are checked during provider work and child-process polling. Tracked yt-dlp and FFmpeg children must be terminated and reaped before shutdown is reported as clean.

The provider-network primary lease intentionally covers source analysis through existing-output reuse or yt-dlp transfer. It is released before independent FFmpeg processing. This prevents optional metadata or queued-preview extraction from overlapping the primary provider path while allowing bounded thumbnail work to remain independent.

`export_planning.py` builds the canonical plan. `output_validation.py` is the single plan-matching contract for both reused and freshly staged media.

## Worker-to-UI event flow

Background work never mutates Tk widgets directly. Producers place typed `(kind, payload)` events onto one FIFO queue. `ui_events.py` owns the event contracts and domain handlers; the Tk thread drains the queue and dispatches events in order.

Transfer events own progress and status. Metadata events update run-owned previews, history, and Library presentation. Runtime events own updater and installation-lifecycle feedback. Terminal events finalize the active run and launch the next queued job. Defensive payload checks remain at the UI boundary because events can outlive the run that produced them.

## Staging and commit boundary

Every fresh output begins in a private `0700` staging directory. Staged media is untrusted until ffprobe confirms the selected plan's container, codecs, dimensions, rate, channels, bitrate policy, and other applicable invariants.

The commit layer resolves the selected root, rechecks containment immediately before mutation, and rejects redirecting or reparse descendant and leaf components. The selected root itself may intentionally be a symlink. Only validated artifacts move into it, and committed metadata must not retain private `.vfstage` paths. Normal worker cleanup covers success, failure, cancellation, and skip; hard process death is recovered or diagnosed on the next lifecycle rather than reported as synchronous cleanup.

## Platform seam

`platform_services.py` owns ordinary OS integration: diagnostics location, file/folder opening, folder picking, runtime discovery and probes, hidden Windows subprocess policy, shortcuts, fonts, icons, and application identity. Durable-data paths and output-containment modules retain the platform checks local to their own contracts.

The updater trust boundary is deliberately separate. An `update_ready` event is emitted only after checksum and applicable platform identity/signature checks, and macOS re-verifies before launch. `DownloaderApp` orchestrates prompts and events; updater modules and release tooling own the trust rules, which must not be weakened behind a generic platform abstraction.

## Packaged application and quality harness

The isolated `engineering-quality/` harness has three non-interchangeable evidence tiers:

- Unit/static checks exercise pure contracts, repository tests, typing, linting, security signals, and bounded mutation probes.
- Headless production-pipeline scenarios call the real worker seam for high-volume correctness, fault, performance, lifecycle, and concurrency evidence.
- Packaged-app E2E drives the real application UI and must independently observe settings, queue, worker lifecycle, cancellation, progress, restart, Library state, and committed outputs.

A successful headless scenario is not evidence that the complete packaged application works. Likewise, an older signed artifact cannot prove source-only UI hooks added after it was built; those observations remain explicitly unavailable until a matching artifact is exercised.
