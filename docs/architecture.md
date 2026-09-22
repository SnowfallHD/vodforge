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
- `playback_backend.py` defines the immutable single-engine player contract; `libvlc_backend.py` owns decoding, audio/video timing, engine state, seeking, and volume; and `playback_surface.py` owns the native Tk-hosted render surface. `media_preview.py` separately owns bounded FFmpeg thumbnail extraction. Missing-media recovery is planned by `library_media_recovery.py` from durable history and a validated saved job profile; UI code cannot reconstruct or guess an output profile.
- UI selection is presentation state. It must not become execution authority.

## UI seams

The composition root owns Forge execution and connects Library/Watch to the
canonical projection and actions. LibraryScene and WatchView own their separate
presentation trees, input targets, and viewport positions. Their extracted seams
are deliberately narrower than application state:

- `focus_settings.py` owns Settings dialog construction and visibility. It receives explicit variables and actions; it does not own the next-run settings values or create jobs.
- `library_state.py` owns the single Library membership/status projection from canonical run, queue, terminal, preview, history, and annotation owners. The application atomically adopts and renders that immutable snapshot; it does not append, remove, or terminalize Library rows.
- Run Deck derives its latest items from that same projection, including each committed playlist item while its successor runs. It has no parallel completed-item ledger.
- `library_search.py` owns render-only search/category predicates. `library_search_ui.py`, `media_player_ui.py`, annotation UI, and missing-media recovery UI each own rendering strategy for their local surface.
- `media_player_ui.py` renders VODForge controls from immutable engine snapshots. It does not decode frames, own an audio clock, or restart playback processes for seek and volume changes.
- `ui_layout.py` owns shared responsive geometry policy. `ui_widgets.py` owns reusable Tk controls and input behavior. `ui_theme.py` owns the shared visual tokens.
- `ChoiceDropdown` and `ChoiceMenu` own application choice fields/popovers on both platforms. System file pickers remain OS-owned.
- `activity_ui.py` owns shared styled technical logs. `forge_activity_ui.py` adds a session-derived friendly-phase view in the same viewport; Activity remains technical. Neither view owns durable run state.
- `whats_new.py` owns the curated catalog and eligibility; `whats_new_ui.py` owns the fixed carousel and lifetime. Native exhibits reuse production widgets without downloads, persistence or playback side effects. See [native preview authoring](whats-new-native-previews.md).

These modules are not independent view models. Execution authority and cross-view selection remain explicit in `DownloaderApp` so a second state system cannot drift from the real queue.

## Shared product and native implementations

There is one product UI, theme vocabulary, input-intent contract, archive authority,
and player state machine. macOS and Windows do not own copies of screens or state.
`platform_services.py` remains the public capability/dispatch boundary; native code
lives under `yt_downloader/platforms/macos` and `yt_downloader/platforms/windows`.
Imports must not initialize the other operating system's native libraries.

| Responsibility | Shared owner | macOS implementation | Windows implementation |
| --- | --- | --- | --- |
| Window integration | Application composition and platform services | `platforms/macos/windowing.py` | `platforms/windows/windowing.py` |
| Player | `libvlc_backend.py`, `playback_surface.py`, presentation contracts | `platforms/macos/player_overlay.py` | `platforms/windows/video_host.py` |
| Update policy and durable recovery | `updates.py`, `update_recovery.py` | Existing signed bundle helper | `platforms/windows/update_recovery.py` (embedded recovery functions) |
| System dialogs/child-process presentation | Platform services | Tk-owned native picker/quit bindings | `platforms/windows/dialogs.py`, `processes.py` |
| Raster surfaces, capture and drawing | `ui_materials.py`, shared geometry/tokens | `platforms/macos/surfaces.py` | `platforms/windows/surfaces.py` |
| File authority | Archive/history/safe-output owners | `platforms/macos/filesystem.py` | `platforms/windows/filesystem.py` |
| Build and native evidence | Shared release/report contracts | Existing `build_macos.sh`, signing scripts and Mac native adapters | Existing `build_windows.ps1`, installer scripts and Windows native adapters |

Build/script entrypoint paths stay stable because CI, signing and release receipts
reference them. Source moves must update package discovery, actual import bindings,
test patch points and bounded diagnostic labels. The moved Mac overlay deliberately
keeps its existing closed telemetry label `player_overlay_macos`; organization does
not expand data collection. OS-specific path/handle security conditions remain with
the correct authority until a bounded extraction can preserve that contract.

Qualification remains separate by OS and artifact. In particular, Windows sharpness
is unresolved: measure display/effective DPI, awareness, Tk scaling, physical capture
and raster backing sizes before assigning cause or changing rendering. A resampled
screenshot or a passing color test cannot establish native-density parity.

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

`export_planning.py` builds MP4/MP3 plans. `original_audio.py` selects a supported
original stream through the shared audio selection logic and supplies stream-copy
options. It emits `AudioExportPlan`, not a separate worker pipeline: Opus becomes
`.opus`, AAC becomes `.m4a`; unsupported source codecs fail closed.
`output_validation.py` owns plan matching for reused and freshly staged media.
Original audio checks codec/source properties rather than an MP3 target bitrate.
Missing exact Original audio paths cannot fall through to legacy MP4 file guessing.

Quality selection resolves the highest eligible provider tier before codec and
transport preferences. A named 1080p stream need not have exactly 1080 image rows.
Fallbacks must not exceed the selected ceiling.

## Privacy and onboarding state

- `settings_store.py` owns `settings.json`, including the user's
  `analytics_consent.choice` and the acknowledged showcase ID.
- `cloud_funnel.py` owns `installation.json`: identity, first-launch delivery
  state, and onboarding markers for region policy, browser eligibility, and the
  welcome attempt.
- `analytics_consent.py` joins those owners and migrates legacy fields.
  `analytics-consent.json` is a migration input, not an ongoing third authority;
  successful migration retires it.
- `analytics_startup.py` coordinates bounded region resolution, the in-app
  permission panel, and one-time welcome handoff. Updating existing installations
  does not make them eligible for first-install attribution.
- Build provenance and consent are both required for optional telemetry. Source
  and ordinary private packages fail closed even with release-like versions.
  Functional update checks are separate from analytics delivery.

Files live in the platform application-data directory. Saved denial persists;
unknown/opt-in policy does not grant permission. Malformed state is preserved and
fails closed instead of replacing identity or implicitly granting consent.

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


## Shared UI capability catalog

See [UI components and behavior](ui-components.md) for input, popup, inline editing and presentation owners. Durable descriptions are nullable local annotation overrides; provider descriptions and personal notes remain distinct. Projection publishes an override only when one exists.


## Repository map and contributor workflow

| Location | Responsibility |
| --- | --- |
| main.py / yt_downloader/app.py | Startup and application composition |
| yt_downloader/library_scene_ui.py / library_scene_layout.py | Library routes, current-owner actions, bounded rendering |
| yt_downloader/watch_ui.py / watch_scene_ui.py | Watch routes, playback callbacks, hero and content rows |
| yt_downloader/scene_rail.py / scene_paging.py | Shared horizontal viewport and bounded visible-range geometry |
| yt_downloader/ui_transition.py | Short top-tab reveal and generation-owned cancellation |
| yt_downloader/platform_services.py | Own-window rendering and ordinary platform integration |
| yt_downloader/archive_artwork.py | Asynchronous decoding, bounded images and retired requests |
| yt_downloader/media_player_ui.py / player_scene_ui.py | One player session and its responsive presentation |
| tests/ | Source and explicitly enabled native regression cases |
| engineering-quality/ | Required defect classes, worker scenarios and artifact-bound gates |
| fine-tuning/ | Encoder experiments and measured preset selection |
| scripts/ | Preview, packaging support and bounded development utilities |
| docs/ | Canonical product/architecture/contributor guides |
| assets/ | Shared product imagery, including the packaged Watch welcome asset |

Follow README Development for environment setup. A focused change should describe
its concrete trigger and resulting behavior, extend existing ownership, preserve
regression evidence, update affected catalog entries, and run the appropriate
required harness class. Native input and final packaged acceptance are independent
gates. AGENTS.md routes automated contributors to these same human-readable guides.

Top-tab transitions prepare a brief blurred cover of the outgoing application
view through native own-window drawing, after releasing an embedded player.
The cover is a sibling of the content views, so changing the selected view cannot
unmap it prematurely. The destination is revealed once, without a delayed blur
of already-visible content. No desktop read, Screen Recording permission, or
production capture file is involved. A generation cancels older timers/overlays;
within-tab navigation and resize end the reveal immediately. Unsupported or slow
capture falls back to immediate navigation. This is an optional visual effect and
does not own tab state, playback or action dispatch.

## User-requested file operations

Library selection and item menus route through library_file_actions_ui. They capture
immutable owners, resolve against all durable history rows, and use the existing
ArchiveWorkOwner lane. archive_file_operations owns exact-file preflight, destination
conflicts, copy verification, Trash/permanent separation and recovery. It reuses
safe_output staging/commit and archive_relink.relocated_records; save_history remains
the only completed-output writer. Local progress keeps its existing key through a
location change; annotation/collection lineage remains separate and unchanged.

A private file-operations receipt records per-artifact intent and observed outcomes.
Move verifies every owned artifact before publishing history and retires originals
only after the actual history file and destination have been flushed. A flush failure
is uncertain even when JSON bytes match. Recovery must establish durability again.
Trash failure never switches to permanent deletion. An exact missing leaf under an
accessible parent permits entry-only removal; offline, denied, redirected, ambiguous
and shared ownership remain distinct. Unknown siblings are never swept into cleanup.

The history authority gates all writers while an operation receipt is unresolved.
Only the active worker has an exception-scoped thread-local write lease for its exact
receipt and exact intended history payload. An unrelated write cannot borrow it. The UI
stages incoming download/activity deltas through the existing pending-history owner,
reloads actual committed history even when the final receipt write fails, and resumes
deferred writers only after recovery settles. Late deltas from that same recorded run
follow its verified moved owner or remain removed after deletion; a new run remains
eligible to publish its own output. Browsing and playback stay available.
Normal/restart Move cleanup share one implementation; a requested but unconfirmed
Trash effect is never blindly repeated. Keeping the current state is an explicit
review outcome, not a claim that an interrupted operation succeeded. If a Delete
already removed a Library entry, Keep as is records that re-flushed history
disposition separately from the uncertain file-effect state, so a late event cannot
recreate it. A finished receipt cannot reopen; pending work blocks the next
operation, preserving the order of receipt modification across valid recovery.

Receipts contain private paths and identity evidence and never enter telemetry.
Unresolved receipts are retained. Completed/reviewed receipts remain throughout
the current producer session so delayed events cannot resurrect retired paths.
At startup, after the previous process is gone and pending deltas are durably
replayed, completed receipts are reduced to the latest 32. Receipt count and
individual read size remain bounded: 4 MiB per receipt, 16 MiB total encoded
receipts, at most 5,000 receipts. New work reserves its full receipt allowance
before media effects. Readers check identities and aggregate sizes before parsing;
a bounded identity-keyed cache avoids repeatedly decoding unchanged receipts.
Reaching a limit fails closed before admitting more file work. They are recovery evidence, not another history
ledger. Source-native file tests use isolated fixtures only. The Windows recycle
adapter requires the modern Send2Trash native backend and refuses its legacy fallback.

## Player media intent and replacement

The application normally creates a new MediaPlayerWindow and backend for each
media launch. The player additionally captures backend identity and the immutable
snapshot's media_generation/path for media-bound UI intent. The backend advances
media_generation before a validated load attempt mutates the provider, including
same-path reloads and attempts that fail after stopping the previous media.
A missing-file rejection before provider mutation does not advance it. Volume and
ordinary seeking do not change media identity.

Absolute seeks, timeline coordinates, chapters and preview positions belong to
that captured media. They retire when the view closes, the backend changes, or a
new load generation replaces it. Admission precedes access to old widgets.
Relative keyboard seeking and volume are current transport intent; they remain
usable against current media while the view is open. A relative command against
a replacement does not update the old media's progress binding or feature receipt.
This local generation is not a new telemetry field or persisted library identity.


Explicit-size artwork cache entries carry their tile/hero dimensions in their
identity. A change to the default media-card size invalidates default-sized
pixels while preserving cached explicit-size entries. This keeps channel avatars
present during Watch resizing without reusing a different-size or different-owner
image. Existing cache bounds, file rechecks, and worker teardown still apply; the
harness guide documents the distinct-owner native pixel regression and its limits.


Before a top-tab cover is removed, ui_transition invokes the existing shared
platform_services.present_pending_drawing owner once per bounded pass for the destination frame.
It covers child canvases and leaf-widget layouts such as Activity. The
present_scrolled_canvas adapter invokes the same implementation only for canvases
with child windows, where scrolling needs explicit drawing. Pending idle work can
invoke navigation or teardown, so transition generation is checked again before
reveal. The helper checks Tcl command lifetime between batches and releases its
reentry guard in finally. Its six-batch/40ms soft limit cannot preempt an individual
callback. A transition may yield 8ms and retry, at most three passes; cancellation
retires the scheduled generation and the final bounded pass reveals even if work
remains. Scrolling retains a single pass. Own-view capture copies validated opaque
RGBA native pixels without PNG encoding, with the original encoder fallback for
other formats. No borrowed native image buffer survives the capture helper.
This application-level ordering uses the installed Tk runtime; native
pixel, successor and teardown evidence and remaining limits live in the harness
guide.


Live Configure rendering may refit a fresh decoded original when a requested
artwork size changes while Tk worker polling is deferred. The shared artwork
owner uses the original RGB image, never an already cropped presentation.
Decoding and storage access remain on the worker; fitting and PhotoImage creation
run on the UI thread and have no hard latency guarantee. The decoded-source LRU
holds at most 16 originals / 64 MiB per view, with a 30-second file-validation
deadline. Worker results independently cap retained originals at the same bounds;
oversized originals still deliver their fitted output through the normal worker.
Rendered reuse holds at most 64 entries / 32 MiB, except one larger current image
is retained so a requested image cannot vanish solely because it exceeds that
reuse budget. Visible images have separate lifetime references. These are cache
budgets, not total process RSS limits.

Metadata and artwork role bind decoded-source identity. Successful unchanged-file
checks renew its eligibility; known-unavailable results retire it. Expired,
evicted, oversized and not-yet-decoded sources require the ordinary asynchronous
path, so this is bounded continuity for fresh cached artwork, not a guarantee for
all workloads. Closing a view clears both caches and retires the worker owner.

CanvasSurfaceCache owns scene surface lifetime across synchronous replacement.
Library and Watch borrow the preceding displayed frame while constructing the
new one, then retire unused references on success or exception. This is transient
display ownership, not an enlarged unused cache. See the
[component contract](ui-components.md#surface-reuse-during-a-redraw) for usage and
the harness guide for independent native RSS qualification.

### Relink review navigation and storage settlement

The active relink panel is identified by its widget identity, independently of
the consent-bound observer (which may be absent). Library/Watch navigation routes
that panel through _archive_cancel_relink, never playback cancellation. During
a pending commit, the existing worker retains its result and completion callback;
the review stays visible until storage reports the outcome. Cancellation before
the atomic save leaves history unchanged; a save already completed is adopted and
reconciled. After settlement, navigation is available again. The panel reference
and its shared KeyboardScope retire with the overlay. No deferred navigation
queue or second history authority is introduced.

Relink observer lifetime ends with the operation, independently of the recovery
panel's lifetime. Verification refusal/failure/timeout and update failure/cancellation/
refusal retire the bound observer; later panel dismissal cannot emit a second
terminal event. Timeout presentation derives display labels from the original
proposal without changing it, while the worker generation rejects late results.

Matte material ownership is centralized in ui_chrome.py; ui_materials.py owns
static motif masks and app-only brand tint. The component catalog owns the mapping
and exceptions. Views delegate material paint and retain their own input/data.

The rejected enclosing Forge panel is not part of the visual contract. Shared
frame background enrollment aligns nested decorative canvases to the same tab
origin and shares one theme texture per top-level window. It changes neither
navigation nor input ownership and does not resample during resize.


### Native read-only text over scene artwork

MatteTextProjection in ui_materials owns presentation over existing read-only
Text and Label widgets. Their documents, variables, geometry, selection and
keyboard bindings remain native; a nonfocusable child canvas paints aligned
artwork and text using native font geometry. Pointer coordinates are forwarded
to the document, and variable/modification/theme/geometry invalidation is scoped
to the owner. Destruction retires pending paint, traces and bindings. It does not
enroll editable fields or change data/selection models. Forge and Activity use this shared adapter. Native viewport notifications keep
scrollbars, keyboard movement and see() synchronized; visible display-row bounds
avoid scanning hidden wide-line tails. Embedded document images and status labels
retain their native owners, and elided tokens remain selectable without being painted.
This is not complete app-wide adoption or accessibility qualification. Historical
direct NSAccessibility inspection exposed AXUnknown and no children before and
after projection. A later v63 read-only external observation used a trusted separate
process, exact QA PID/window title, and visible nonblank control assertions.
ProductEntry, readonly FactsText, EditableTextSection text and the ActionDialogSurface
footer each had verified Tk focus, but AXFocusedUIElement remained AXWindow.
The external tree exposed window chrome/title/groups rather than these controls'
roles or values.

The identical application fixture and reader reproduced this on stock and composed
Tk 9.0.4 under the same interpreter/Tcl library, with loaded library hashes retained.
Thus the combined Tk patches are not necessary to reproduce the gap. The comparison
does not distinguish stock toolkit behavior from application composition. It is
stopped with that uncertainty explicit: no new accessibility adapter or architecture
has been introduced. Successful observation execution is not screen-reader usability,
VoiceOver, installed-app or Windows acceptance. Physical assistive-technology behavior
and a scoped root-cause/repair proposal remain separate requirements.

The source-native regression uses an independent two-tone background to amplify
seams, inserts a real opaque rectangle as a negative control, and checks native
selection, resizes and teardown. A prior hide-overlay control failed to produce
a visible fault on the tested Tk runtime; that failed evidence is retained.
Add active/completed/error states, theme changes, long documents and keyboard/
accessibility/performance checks when extending this owner. Keep physical-pixel
captures and their backing-scale metadata alongside logical previews.

The existing history publication owner opens its committed file in nontruncating
read/write mode for the final durability flush, because Windows FlushFileBuffers
requires a write-capable handle. This does not add a second content writer or
weaken atomic publication. Optional Tk input sequences are queried through
platform_services before callbacks are registered; ui_scrolling and ui_transition
retain their shared wheel/navigation behavior on interpreters without that event.
