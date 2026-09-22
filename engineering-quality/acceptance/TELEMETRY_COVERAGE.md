# Full application telemetry coverage and diagnostic review

Required by the September 18 user scope addition. This is an acceptance inventory,
not a claim of complete instrumentation. Overall status: **unproven**.
The canonical operating standard is [HARNESS_GUIDE](../HARNESS_GUIDE.md);
production ownership and privacy contract are in
[telemetry-features](../../docs/telemetry-features.md).

For every row qualify intent/admission, progress and latency, outcome, errors,
cancellation/abandonment/recovery where meaningful; correlate within a consent
epoch with exact build/platform and bounded configuration. Name authoritative
producers, scenario assertions, fault controls, raw source-bound evidence and
stored queries. State the denominator and what a query cannot conclude.
“Unproven” includes missing audit or evidence, even when events already exist.

| Required journey | Diagnostic/usability question | Qualification |
| --- | --- | --- |
| Startup/bootstrap/first paint | Did initialization finish; where did admission or readiness stop? | Unproven |
| Consent/settings/migrations | Did the chosen setting persist; was collection authorized throughout? | Unproven |
| Automatic/manual update | When was checking dispatched; was provider/offline/verification/handoff responsible? | Source/native prompt-dispatch check passed; whole journey unproven |
| Download recovery | Which typed stage/cause blocks start; did safe recovery preserve ownership/history? | Fourteen actual startup/restoration/runtime-refusal producer fixtures passed outbox and authenticated local D1 readback, identity, duplicate and privacy checks; full journey/denominator and deployed evidence remain incomplete |
| Forge URL admission/preview | Was input admitted, rejected or abandoned; did preview become ready? | Unproven |
| Local MP3-to-video | Did selection/validation/conversion/commit succeed; are failed steps distinguishable? | Unproven |
| Presets/output choices | Are available choices understood and honored by actual output? | Unproven |
| Queue/batch/playlist | What entered, waited, advanced or was removed; which item failed? | Unproven |
| Download/retry/skip/cancel | Does each attempt resolve correctly; do retries preserve ancestry? | Unproven |
| Export/validation/reuse | Was output independently validated and committed or safely reused? | Unproven |
| Library discovery/search/filter | Did intent reveal matching content or a recoverable empty/no-op state? | Unproven |
| Channels/playlists/collections | Do sparse and dense collections remain useful and navigable? | Unproven |
| Notes/tags/descriptions | Did a meaningful edit commit without collecting its content? | Unproven |
| Source/output details | Can users find relevant summaries and disclose needed detail? | Unproven |
| Storage/volumes/import | Is unavailable storage distinguishable from invalid input or write failure? | Import consent lifetime and completion/failure/cancellation have actual producer/outbox and authenticated local stored-query coverage. Refused worker submission now has a real-owner regression proving terminal status with no polling or history effects. Saved-folder check consent and completion/missing/timeout/cancel callbacks now have real producer/outbox and authenticated local readback/replay coverage. Other stage attribution, progress, native selection, storage/volume and exact-package coverage remain unproven. |
| Move/delete/relink/missing media | Were requested effects committed, refused or cancelled with safe recovery? | Relink review cancellation has six native consent/observer contexts with before/pressed/after captures and actual offline producer readback/replay; Worker refusal, queued cancellation, forced-deadline timeout and verification refusal/failure/timeout have thirty-six native consent/observer contexts through settled review dismissal, late-result rejection and actual offline producer readback/replay. Verified-file success, executed commit outcomes, platform/storage and deployed delivery remain separately unqualified. File-action dialog consent lifetime, preview error/timeout visibility and analysis/commit stage attribution have producer/outbox regression coverage; other effects, native/platform and deployed qualification remain unproven. See telemetry-features for the bounded fixture and query limits. |
| Watch home/hero/rails | Can users discover and start saved content; where do journeys stop? | Unproven |
| Player readiness/playback/replay | Was provider readiness followed by advancing playback and truthful outcome? | Unproven |
| Seek/volume/captions/chapters/preview | Was current intent applied; did replacement retire stale callbacks? | Unproven |
| Fullscreen/floating/return | Did surface ownership transfer and return without losing controls? | Unproven |
| Cast capability | Verify whether supported; exclude with evidence if absent rather than inventing events | Unproven |
| Navigation/popups/Back | Did destination/context remain clear; are dead ends and no-ops observable? | Unproven |
| Keyboard/focus/disclosure | Are controls reachable and labels comprehensible without hover? | Unproven |
| Scroll/resize/render/artwork | Separate input receipt, callback cost, render completion and presented pixels | Pending-audit deadline defect repaired; real Tk producer/outbox and authenticated local replay/readback/query covered. Audit delay is not presentation latency. Sustained performance, packaged/deployed paths and original release failures remain open; see [query and limits](../../docs/telemetry-features.md#presentation-audit-scheduling-delay). |
| Persistence/history/annotations | Were writes atomic and durable; could an error poison future operations? | Unproven |
| Workers/process ownership | Were requests scoped correctly; did cancellation and teardown prevent late effects? | Unproven |
| Shutdown/restart | Were unfinished operations preserved and late observations retired safely? | Unproven |
| Telemetry outbox/credentials/transport | Was an event queued, retried, rejected or delivered; can loss be bounded? | Unproven |

## Evidence and query requirements

- Use actual producer payloads through authenticated ingestion and exact stored
  readback. Synthetic vocabulary iteration is a compatibility test, not producer
  qualification. A local D1 test is not a production deployment receipt.
- Test pre-initialization and late-shutdown faults, delays, duplicates, offline
  retry, revocation, disabled consent, transport failures and missing observations.
- Provide queries that distinguish attempts from events, retries from new intent,
  and an unavailable measurement from zero. Sampled UI events cannot supply an
  unsampled population denominator.
- Keep telemetry failures from recursively creating more telemetry. Document the
  resulting visibility limit and use bounded local health evidence where delivery
  itself is unavailable.
- No raw keystrokes, content, screenshots, files, filenames, URLs, paths or secrets.
  Record deliberate exclusions and their effect on diagnosis. Do not promise that
  every future bug can be diagnosed without any user-supplied evidence.

Missing required qualification blocks acceptance under the harness's current
fail-closed interaction-coverage migration. This inventory cannot waive those
blockers or qualify a candidate through a documentation-only status edit.


The recovery query example and its limits live in
[telemetry semantics](../../docs/telemetry-features.md#query-utility-and-denominator-limits).
An authenticated stored-query control distinguishes repeated refusal operations
from one affected attempt despite duplicate delivery. Successful-admission
denominators and subsequent resolution correlation remain unproven; this is not a
family-wide completeness claim.

Run-menu admission now has a bounded producer-to-stored-readback path:
three active-run menu intents, current/retired owner outcomes, consent denial and
withdrawal, offline outbox and telemetry exception controls, exact authenticated
D1 readback and duplicate-safe operation query. See the run-menu section of
telemetry-features.md. Whole Forge control coverage, within-run item rollover,
other surfaces and actual worker-stop outcome correlation remain open.

Resize context now retains the originating view and library-size bucket;
Watch is explicitly classified. Six before-fix producer failures and corrected
real-outbox/authenticated local readback/replay/query controls cover delayed
settlement after navigation. See [resize semantics and limits](../../docs/telemetry-features.md#resize-burst-origin-and-query-limits).
This repairs observation attribution; it does not repair or close the original
Library resize delay, physical pointer report, or whole-family coverage.
