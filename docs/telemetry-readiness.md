# Telemetry readiness and practical limits

## Current status — 2026-09-29

The Qt wiring gaps found in the latest audit are repaired: file-management usage,
metadata-preview outcomes with structured failures, and player resume/progress
correlation. Core navigation now records repeated visits as consent-bound
operations. Qt playback retains the provider's closed error enum, observed origin
and elapsed-time bucket. Update checks, offers, explicit Later, dismissal,
download/verification, blocked installation, helper handoff and verified next-launch
receipts are correlated. Failures retain bounded machine facts before friendly
copy replaces local error text. These are separate from exact packaged client
qualification. See the maintained coverage inventory for receipts and their tiers.

The installed Qt development preview is compiled with telemetry disabled. Source
instrumentation cannot make that artifact collect. Do not call the full new Qt
release qualified until a telemetry-enabled candidate has completed its Mac and
Windows consent, feature, failure, restart and deployed-ingestion journeys.
Existing successful historical release receipts apply to their named artifacts.

## What remains, and what would solve it

| Limitation | Category | Practical solution / limit |
| --- | --- | --- |
| Qt owners omitted existing observations | Wiring, repaired | Reuse existing consent-bound producers; prove actual serialized and stored outcomes, not only vocabulary. |
| Engagement records presence, not every visit or click | Core navigation repaired | My Files / All media / Issues, folder opening, Library opening/selection and Watch opening/channel selection now emit repeated bounded visits. Other decorative clicks remain deliberately outside this funnel. |
| Qt playback failure lacked its native category | Repaired | Actual QMediaPlayer error enum is passed to the consent-bound operation. Resource/format/network/access-denied/unknown remain distinct. Resource is not automatically a filesystem diagnosis. |
| Some stage/config/environment facts or timing are unavailable | Bounded context expanded | Existing effective run configuration/build/platform and typed failure facts are retained. Updates add from/target version, automatic/manual/repair trigger, blocker and elapsed-time bucket. Player failures add origin/surface/time. Nearby settings are not proof of causal influence. Arbitrary future faults may require another bounded fact. |
| Remaining journey inventory says unproven | Verification work | Inspect the authoritative producers and qualify the exact packages against actual effects and stored queries. This status includes absent evidence, not necessarily missing events. More data cannot substitute for running those checks. |
| Hosted analytics investigation interface | Defined analysis supplied | Read-only D1 reports classify update outcomes, group failures by exact build/callsite/machine facts and count repeated core visits. An interactive dashboard or automatic alert service remains a tooling decision; event volume does not create it. |
| No native Qt visual replay or native crash dump/symbolication pipeline | Substantial separate capability | Feasible engineering, but not a small payload addition. Native recording needs privacy, masking, platform support and resource budgets; crash diagnosis needs native artifacts/symbols and delivery. Do not describe web replay as Qt support. |
| Installation identity is not a cross-device person identity | Deliberate measurement scope | Current counts describe consenting installations/sessions. Account-based user analytics would require an explicit identity/privacy decision. |
| Exact source/provider account, cookies, paths or user media unavailable | Deliberate privacy boundary | Request narrowly scoped voluntary support evidence when needed. Automatic transmission of private sources, credentials or content is not a reasonable completeness target. |
| A visual defect emits no error; a source changes; a device-specific codec/GPU race differs locally | Reproduction limit | Structured context narrows candidates. Screenshots, native reproduction or optional deeper support logs may still be required. More logs cannot guarantee determinism. |
| Crash before persistence, full/offline outbox, no later launch, or consent off | Measurement limit | Durable retries and bounded drop observations help, but absence is unknown. The current outbox is capped at 256 events, 512 KiB and 30 days; operation observations are capped at 64. No client telemetry is a complete census. |

These categories overlap, so a percentage of “solvable by more data” would be
misleading. The concrete wiring/context gaps above are solved in source. Package/native
qualification remains required before a release claim. Native replay/crash dumps
and guaranteed private-source/device reproduction are explicitly excluded from
this pass. Consent, private-content boundaries and unknown observations remain
intentional limits, rather than missing instrumentation.

## PostHog comparison

PostHog provides product analysis, error grouping and investigation tooling. Its
Python error SDK can capture exceptions; its documented replay integrations
primarily target web and mobile frameworks. The documentation reviewed here does
not establish native Qt autocapture/replay support. VODForge would still need
explicit events from download, queue, recovery, persistence and player owners to
express meaningful intent, truthful outcome and cancellation. An SDK cannot infer
those semantics from a button click.

References: [error tracking](https://posthog.com/docs/error-tracking/start-here),
[session replay and SDK scope](https://posthog.com/docs/session-replay).

The next useful standard is a defined coverage contract: every enabled core
journey has an intent, admitted work, truthful outcome, bounded failure cause and
operation identity; original consent applies through settlement. Each required
journey must have producer-to-stored-query proof and honest missing-data semantics.
Maintain this in the existing [coverage inventory](../engineering-quality/acceptance/TELEMETRY_COVERAGE.md),
not a second event owner or an assertion that every interaction is captured.

## Update interpretation and startup

The frozen Qt app schedules its first check on the next event-loop turn (zero
intentional delay). Active work no longer postpones this check. A concurrent
updater operation retries after 30 seconds. The actual HTTP result can take time;
zero-delay scheduling does not promise an instantaneous network response.
Installation still waits for active and queued work to finish.

Only an explicit Later records deferral. Closing the popup records dismissal with
unknown intent. Available is provider discovery; shown requires the actual popup.
A helper handoff is not success. Relaunched requires the existing executable-byte
receipt verification, and a Repair failure never records repair completion.
Attempts started without permission, or revoked before settlement, cannot adopt a
later grant. Automatic private sources, raw messages, paths and credentials remain
excluded.

The maintained [D1 reports](../../vodforge-site/docs/telemetry-update-analysis.sql)
are exercised against actual producer fixtures and exact stored rows. They
classify missing later observations as unknown; they cannot infer that a user
chose not to update from silence. Old clients cannot emit this new funnel.
