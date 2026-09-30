# Telemetry readiness and practical limits

## Current status — 2026-09-29

The Qt wiring gaps found in the latest audit are repaired: file-management usage,
metadata-preview outcomes with structured failures, and player resume/progress
correlation. Focused source tests and four real-producer scenarios through the
local authenticated Worker/D1 path pass. The compatible server accepts the new
Issues label. These are separate from exact packaged client qualification.

The installed Qt development preview is compiled with telemetry disabled. Source
instrumentation cannot make that artifact collect. Do not call the full new Qt
release qualified until a telemetry-enabled candidate has completed its Mac and
Windows consent, feature, failure, restart and deployed-ingestion journeys.
Existing successful historical release receipts apply to their named artifacts.

## What remains, and what would solve it

| Limitation | Category | Practical solution / limit |
| --- | --- | --- |
| Qt owners omitted existing observations | Wiring, repaired | Reuse existing consent-bound producers; prove actual serialized and stored outcomes, not only vocabulary. |
| Engagement records whether a feature was used, not every visit or click | More structured data | Use bounded operations for specific funnel questions. Current session-deduplicated events cannot provide click frequency or ordered user paths. No raw clickstream is required to answer core download/recovery outcomes. |
| Generic Qt playback failure has no native error category | More structured data | Carry allowlisted QMediaPlayer error enums at the actual provider callback. More event volume alone cannot identify the cause. |
| Some stage/config/environment facts or timing are unavailable | More structured data | Add only bounded effective configuration, dependency/build facts, provider status and monotonic stage timing tied to the original operation. Settings nearby in time are not proof of causal influence. |
| Remaining journey inventory says unproven | Verification work | Inspect the authoritative producers and qualify the exact packages against actual effects and stored queries. This status includes absent evidence, not necessarily missing events. More data cannot substitute for running those checks. |
| No automatic exception grouping, dashboards, funnels or alerts comparable to a hosted analytics tool | Analysis/product tooling | Existing D1 data can support defined queries. A service can supply these tools; adopting it is a separate architecture decision, not an instrumentation fix. |
| No native Qt visual replay or native crash dump/symbolication pipeline | Substantial separate capability | Feasible engineering, but not a small payload addition. Native recording needs privacy, masking, platform support and resource budgets; crash diagnosis needs native artifacts/symbols and delivery. Do not describe web replay as Qt support. |
| Installation identity is not a cross-device person identity | Deliberate measurement scope | Current counts describe consenting installations/sessions. Account-based user analytics would require an explicit identity/privacy decision. |
| Exact source/provider account, cookies, paths or user media unavailable | Deliberate privacy boundary | Request narrowly scoped voluntary support evidence when needed. Automatic transmission of private sources, credentials or content is not a reasonable completeness target. |
| A visual defect emits no error; a source changes; a device-specific codec/GPU race differs locally | Reproduction limit | Structured context narrows candidates. Screenshots, native reproduction or optional deeper support logs may still be required. More logs cannot guarantee determinism. |
| Crash before persistence, full/offline outbox, no later launch, or consent off | Measurement limit | Durable retries and bounded drop observations help, but absence is unknown. The current outbox is capped at 256 events, 512 KiB and 30 days; operation observations are capped at 64. No client telemetry is a complete census. |

These categories overlap, so a percentage of “solvable by more data” would be
misleading. The three concrete wiring gaps are solved. Most additional *diagnostic
context* can be added as structured facts; comprehensive *qualification*, native
replay and private-source reproduction require different work.

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
