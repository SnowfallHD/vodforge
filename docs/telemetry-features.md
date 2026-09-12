# Product telemetry ownership and feature contract

Optional analytics measures feature use and outcomes. It does not collect media
URLs, IDs, titles, paths, filenames, queries, notes, tags, category names, playback
positions, raw colors, GPU identifiers, or error prose. Consent, artifact policy,
preview isolation, immutable credentials and bounded retention still apply.

## Owners

| Responsibility | Owner |
| --- | --- |
| Closed feature/action and dimension vocabulary; bucket/projection policy | `yt_downloader/telemetry_features.py` |
| Event names/schema, installation-scoped attempt IDs, consent, session engagement deduplication, timing and retry outbox | `yt_downloader/product_telemetry.py` |
| Authentication, launch authorization and transport retry | Existing `telemetry_credentials.py` / `telemetry_transport.py` |
| Actual feature actions and outcomes | Existing Library, player, conversion, showcase and update UI owners; app composes callbacks |
| Update outcome receipts and current-executable confirmation | Existing `updates.py` helper and receipt functions |
| Validation, compatibility and immutable D1 storage | Site `product-telemetry.ts` / `enrolled-telemetry.ts`; migration 0015 |
| Local cross-language/HTTP/D1 contracts | `quality_harness/telemetry_checks.py` |
| Fixed remote preview serializer probe and final-artifact release evidence | `telemetry_feature_probe.py` and `telemetry_release.py` respectively |

Do not add another event dispatcher or run-state owner. New features use callbacks
at the existing authoritative success/failure boundary. Export fact projection
belongs in the vocabulary module, not widget handlers. The backend harness fails
if Python and TypeScript vocabularies drift. The provider reuses the desktop event
names and dimension validator rather than maintaining its own event catalog.

## Schema v2

`attempt_id` is derived from the installation's random identity and the local run
key. It exposes neither the local key nor the source. `retry_of` references the
previous opaque attempt. The existing run journal preserves explicit execution and retry links. A playlist
item presentation can belong to a parent execution without itself being a retry.
No second attempt registry is introduced. Different installations
produce different IDs for the same local key.

Runs emit start and terminal events; `run_completed` distinguishes `complete` and
`partial`. Queuing, removal before start, actual item skip, and each validated media
commit have separate events. A playlist has one attempt and multiple media exports.
Recovery of interrupted attempts reports the persisted terminal state. A closed
app that never reopens cannot report a crash outcome.

Exports report the preset, successful command's encoder and rate-control mode,
source/output resolution tiers, duration and size buckets. Original audio reports
`original` / `copy`; an MP3's embedded cover does not count as video resolution.
MP3 artwork uses `none`, `thumbnail` or `custom`, never an image path. Input kind
and known URL-list size are bounded. Unknown playlist length is omitted rather
than reported as one item. Local conversion emits starts, failures, cancellations
and canonical-history-confirmed completion with measured output dimensions.

Processing time means elapsed worker time, including download/validation/commit;
queue wait is separate. Timings use a monotonic clock in the telemetry owner and
are omitted when their start was not observed in this process. They are not
encoder-only benchmark measurements. The outbox remains limited to 256 events,
512 KiB and the existing 30-day delivery acceptance window.

Deduplication suppresses new event creation, not delivery retries: repeated
startup or feature callbacks retry any existing immutable queued event. A producer
request received while the delivery worker is finishing must wake that worker or
start its replacement. The release journey requires app-open delivery while idle,
before a later feature action could mask a stranded queue.

Library discovery/organization, player controls and completion/failure,
missing-media recovery, announcements/Try it, Technical disclosure and appearance
use `feature_used` with a closed feature/action pair. Engagement records presence
once per permitted process session/action, not every keystroke or polling tick.
Search and annotation text is never an event field. Theme names are enumerated;
a custom accent is represented only as `custom`.

Playback failures follow the provider's error event even when libVLC subsequently
reports `Ended`. The existing playback backend retains that error until a new
load or retry; the player reports failure rather than completion. Provider
callbacks do not wait on the lock used by native playback operations.

Updater actions are individual observations. Download, handoff, failure stage,
relaunch and repair are distinct. A successful relaunch requires a helper receipt
and matching executing bytes. Failed Windows handoffs retained after Later can be
reported on the next open of that exact app target. Original helper receipts remain
untouched; a companion marker means the observation was queued in the existing
outbox, not that D1 delivery succeeded. Permission must have been enabled at the
handoff and still be enabled when reporting; later consent cannot backfill an
update started with analytics off. If permission is withdrawn before observation,
a per-action discarded marker prevents a later opt-in from backfilling that result.

## Compatibility and release order

Keep schema v1 ingestion and outbox replay for older released apps. Never relabel
legacy null formats or invent old attempt relationships. Deploy the additive
compatibility migration and backend before publishing a schema-v2 desktop release.
The production deployment and app release are separate from preview testing.

Every addition requires: closed-field privacy rejection tests; a real producer
regression; outbox/retry/consent coverage; backend normalization and D1 readback;
and native action evidence in both final signed release artifacts against preview
D1. See [the release gate](../engineering-quality/TELEMETRY_RELEASE_GATE.md).
A direct serializer probe is deliberately labeled source/transport proof and
cannot satisfy the packaged release gate.
