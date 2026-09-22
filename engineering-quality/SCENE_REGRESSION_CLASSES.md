# Required scene regression classes

NORMAL and DEEP require every class in
[scene_contract.py](quality_harness/scene_contract.py). That registry owns current
selectors, minimum counts and required semantic identities. Do not duplicate
changing counts here. The runner binds production/probe hashes before and after,
isolates HOME, and rejects missing, failed or skipped required tests. Passing
unrelated cases cannot replace a required invariant.

## Maintained classes

| Class | Required behavior |
| --- | --- |
| file_action_integrity | Exact owners/files, verified Move publication before cleanup, Trash/permanent separation, late-event lineage, recovery and resource bounds |
| shared_scroll_ownership | Fractional mouse/trackpad input, nested forwarding, independent targets and teardown |
| shared_keyboard_ownership | Nearest active scope, one action per key, editing keys and restored modal grabs |
| shared_pointer_ownership | Captured press/release, drag rejection, replacement and retired gestures |
| readable_descriptions | Full text, hanging indentation, bounded internal scrolling and complete copying; ellipsis fitting stops measuring after visible-line overflow while full-document counting remains exact |
| library_restraint | Contextual actions, one item menu and current-owner dispatch |
| watch_queue | Canonical identity, readiness, cancellation, presentation transfer and terminal outcomes |
| window_chrome | Native title/fallback, initial geometry, reveal generations and teardown |
| channel_membership | Provider-scoped membership, saved variants, truthful types and selected-playlist counts |
| channel_artwork | Current identity, bounded lookup, network admission and retired results |
| artwork_fidelity | Requested role/geometry, bounded decoding, source changes, eviction and visible rail images |
| progress_lifetime | Acknowledged position, durable writes, resume limits and retired-player isolation |
| volume_truth | Discovered names/types, honest unknowns, canonical paths, duplicate labels and actual capacity |
| bounded_navigation | Complete catalogs/rails, bounded drawing/cache, search scope and actual-origin return |
| import_integrity | Valid local media, preserved metadata, durable publication and failures |
| detail_geometry | Actual text allocation, compact/wide headers, source/output facts and inline controls |
| annotation_ownership | Current item/version, description provenance, tags and return context |
| history_publication | Durable save before adoption, write-failure retention and deferred deltas |
| player_related | Playlist order, saved variants, current-item exclusion, sparse states and retired callbacks |
| player_presentation | Fit/Fill/captions, transport, preview, native/Tk separation and lifecycle |

## Native interaction and rendered playback

[native_ui_checks.py](quality_harness/native_ui_checks.py) enrolls the complete
source-native suite. Require a complete JUnit report without failures, skips or
errors and record source/harness imports. Tests isolate app data and media.
Identify generated Tk events and OS-injected input; neither certifies physical
mouse/trackpad behavior.

Real media cases independently observe advancing rendered frames, transport and
release across embedded, fullscreen, floating and return. A Playing state or
provider clock is insufficient. Queue cases include video/audio/video transfer.
File decisions use real isolated filesystem effects through the actual menu,
confirmation and worker. Real system Trash has a separate unique fixture with
exact restoration; fake-Trash cases do not claim OS integration.

## Recovery and resource limits

Tests vary copy/hash/history/flush failures, cancellation, replaced sources and
receipts, interruption after unlink or cleanup-folder removal, and fresh-process
recovery. Matching JSON bytes do not prove a successful durability flush.

Late events from the same run follow repeated moves and remain deleted after
Move followed by Delete. Finished receipts remain for that producer session.
Startup replays durable pending events first; a recovery gate or replay failure
prevents retirement. A new run can publish its own fresh output.

Readers and writers enforce per-file and aggregate encoded-byte bounds before
effects or parsing. Admission reserves recovery growth. Decoded caching is
bounded by encoded input size and count; Python heap size must be measured
separately and must not be described as equal to the encoded-byte limit.

## Observations and evidence

Optional telemetry reuses consent, provenance, operation and outbox owners.
Only closed-vocabulary outcomes and bounded counts are permitted; paths, titles,
searches, descriptions, tags and positions stay private. Observer failures cannot
change media or history outcomes. Backend checks accept the exact client schema
and reject unexpected content.

For source-bound local playback-control ingestion:

    python -m quality_harness.player_control_probe --site <backend> --output <new-dir>

The loopback Worker/D1 probe binds client, harness, server and migration hashes;
checks actual stored outcomes, denied consent and duplicate delivery; and does
not replace native or final-artifact telemetry acceptance.

Preserve failures and before-fix reproductions. Successors require their own
source identity and applicable checks. Historical receipts remain historical;
do not append conflicting current requirements to this guide.

Source, native GUI, physical-device and exact installed-package checks are
separate tiers. Public release additionally follows [RELEASE_GATE.md](RELEASE_GATE.md)
and both-platform telemetry requirements. A private Mac replacement does not
certify Windows, public signing/notarization or external playback devices.

The caption compatibility behavior keeps Fit while subtitles are active and
restores prior Fill only after subtitles-off readback, unless the user explicitly
chose Fit. It is a reversible layout safeguard, not a new subtitle renderer.
