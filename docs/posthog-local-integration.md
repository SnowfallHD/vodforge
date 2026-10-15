## Current comprehensive successor — October15 evening

The new authorized implementation is additive. See [desktop contract](posthog-desktop-contract.md) for the exact current schema, privacy boundaries, supported native alternatives and QA classification. Historical acceptance notes below retain their original scope. Earlier packages do not contain these successor changes.

Fresh separately resolved provider policy may default ordinary analytics on only where the parent-reviewed regional service permits it; explicit general/provider refusals always win. Old generic cached defaults cannot enable PostHog. Product event names and the authoritative first-party owner/outbox/acknowledgements remain unchanged. PostHog additionally receives safe session context and lifecycle events, standard screen events, categorized manual error tracking and existing processing/UI-performance categories. Qt-native visual replay is unsupported by the documented SDK set; the supported alternative is a semantic event timeline, without content capture. QA uses explicit test labels and independent first-party/provider readback; no adoption is inferred.

The earlier “separate explicit choice everywhere” statements below describe the previous candidate, not the jurisdiction-aware successor. No negative preference is migrated to permission. No prior provider proof is relabeled as successor packaged verification.

# PostHog integration and release qualification

Project 664300 (VODForge), US ingestion, is bound to the authorized public ingestion key. This is not a management credential. Desktop capture is enabled in the reviewed configuration after Cooper’s release authorization; `VODFORGE_POSTHOG_ENABLED=false` remains an emergency opt-out. Separate provider consent is still required; no existing permission is upgraded. Replay and experiments remain off. Website activation and deployment are owned by the canonical site lane.

## Desktop

An additional, explicit PostHog choice is independent of existing VODForge analytics permission. Existing/default consent never grants it. Both permissions and an enabled build are necessary. A new provider epoch on each choice prevents old queued events being mirrored after revocation or reenrollment. The existing custom queue and acknowledgement remain authoritative; PostHog gets one best-effort attempt per admitted event, with a stable top-level event UUID and insert ID. Provider failure does not prevent custom acknowledgement or retain a successfully delivered custom event. In-flight requests cannot be recalled; a crash before persisting the attempt may repeat the same insert ID.

The adapter mirrors the existing 15 product event types, including feature_used, export/run outcomes and updater outcomes. It validates the existing 28 feature groups / 215 approved feature-action pairs. It forwards only version, platform, process architecture, release channel, approved feature/action, run/output category and approved failure reason. It additionally forwards only allowlisted enum values for processing/wait/media-duration/size buckets, preset, encoder, rate control, input kind, resolution, outcome and updater stage, plus validated failure stage. It excludes all other dimensions and raw failure details. IDs are namespace-hashed installation UUIDs. No title, URL, path, private text, cookie, clipboard, email, stack, command, screen recording, replay SDK or hardware fingerprint is sent.

`vf_app_first_run_confirmed` requires a new successful first-party first-launch acknowledgement with provider permission retained from admission to completion. Already-confirmed installations are never backfilled. It is separate from app_opened and from a browser claim. The optional startup checkbox defaults unchecked. Settings remains the existing shared UI.

## Website

PostHog JS is pinned to 1.438.9 and dynamically loaded only after separate provider opt-in plus VODForge permission, with GPC/DNT respected. Remote defaults cannot enable autocapture, exception stacks, page URLs, performance, console recording, person profiles or external dependency loading. Manual events have a closed property vocabulary; unknown fields are discarded. Browser IDs are namespace-hashed random IDs, unrelated to desktop IDs. Withdrawal clears pending intents and experiment observers; a new browser identity resets the provider identity.

Manual events: vf_web_page_viewed, vf_web_feature_used, vf_web_download_clicked, vf_web_download_requested, vf_web_install_help_viewed, vf_web_install_step_viewed, vf_web_installation_link_confirmed, vf_web_failure and vf_experiment_exposed. Browser failures contain categories only. Confirmed browser-link events follow an actual successful existing claim response; no installation ID or capability is forwarded.

Replay additionally requires its own opt-in and build switch. All visitor-entered input values and explicitly tagged private/personal text are masked. Public copy and controls are preserved through a build-reviewed static text/attribute allowlist; unapproved DOM additions are masked or dropped. Email result text, waitlist membership status and claim status are tagged data-ph-mask, while challenge/private sections use data-ph-block. Video/audio, canvas, SVG, frames and private areas remain blocked; only approved static public artwork is retained. Query/hash and claim/desktop/support pages are excluded. Network requests, bodies, headers, console, plugins and custom replay events are dropped. A final structural allowlist retains approved public text and control attributes, drops arbitrary keys, rejects input values/private URLs and masks unknown text. The safe manifest is generated with scripts/generate-replay-public-content.py after a QA build, followed by rebuilding and verifying the reviewed data. Useful masked visual replay still needs private acceptance before activation.

## Installation help and proposed experiments

`/install/` retains the VODForge theme, Mac/Windows keyboard tabs, signed-release choices and truthful requirements: Apple Silicon macOS 26, Intel macOS 15, Windows 10/11 x64. Portable Windows instructions keep the complete extracted folder. It never advises disabling OS security. Direct help views do not request a download. Only a validated platform/build with explicit start=1 requests the existing official download route. This means request, not transfer completion or installation success.

Two experiments are staged, not created or activated: `vf-download-button-color-v1` control/mint; `vf-install-help-v1` control/install-help. Flag payloads must match those variants. Exposure is recorded only when the affected primary button is actually visible. The help variant intercepts only ordinary unmodified same-tab primary download clicks; alternate/new-tab choices remain intact.

Suggested funnels: visible exposure → validated download click; help view → viewed platform instructions; permitted claim response → browser link confirmed. Desktop first-run acknowledgement is a separate observation, not a click-to-install join. No browser can prove binary completion or OS installation from a click or iframe response. Existing supported first-party attribution remains authoritative; missing joins stay unknown.

## Acceptance before activation

Project privacy settings are verified by the parent. Preserve those settings and the existing30-day retention; the remaining replay acceptance is the actual masked/public-content recording outcome. Cooper explicitly accepted default PostHog budgets at2026-10-14 10:47:48UTC; leave budgets unchanged and do not require $0 caps or additional billing scopes. Client IP suppression is defense in depth, not proof that provider transport sees no IP. Original project metadata had anonymize_ips=false; the parent has now independently verified anonymize_ips=true, supported private-text/input masks, console capture off, headers/bodies off, and replay still disabled. Billing caps were not readable with available scopes, which is no longer an activation blocker after Cooper accepted the defaults. Do not expand permissions or change billing.

Cooper now authorizes activation and publication. Desktop capture is enabled in source with separate consent retained; bounded live synthetic acceptance is recorded below. Final signed runtime qualification and the site’s own deployment evidence are still required. Public 0.2.5 remains available until the final 0.2.6 gates pass. Replay/experiments remain disabled.


## October15 release acceptance update

The publication hold was lifted by Cooper, with public Mac requirements unchanged
until actual Apple Silicon macOS15 qualification. Existing recovery.5 artifacts
remain development-labelled and predate these analytics changes; they cannot be
relabeled as the final analytics-enabled release. Final Windows signing and
source/public version sealing remain necessary. No app release is claimed here.

The first synthetic capture probe (test channel only) reproduced two received
rows for two requests sharing only properties.$insert_id. The corrected payload
also sends top-level uuid=event.event_id; two identical UUID5 submissions both
acknowledged200 and independently read back as ONE matching UUID/event/timestamp.
Original failure retained. This proves bounded transport/deduplication, not
native opt-in UI, a packaged runtime launch, real downloads, activation or
retention. Receipt: build/recovery-20261011/posthog-release-20261015/.

26 affected source tests pass, including separate consent, old epoch refusal,
provider failure independence, first-run acknowledgement boundaries, safe
projection, invalid performance values and release configuration opt-out.
Prior tests inspected the local insert ID only and missed the capture API UUID;
local mocks cannot establish provider deduplication. Preserve actual acceptance
alongside source request-envelope assertions for future transport adapters.

The optional project-get settings read was rejected by automatic approval review
because the response can include a project token. It was not retried or bypassed.
Existing public-key/project binding and permitted event query access work. This
optional settings-read gap does not by itself block release.

## Measurement contract

All dashboards exclude release_channel=test/development for product conclusions.
The synthetic probes are technical health fixtures and must never count as users
or adoption. No browser-to-app or cross-device identity join is asserted.

| Question | Event or fields | Honest boundary |
|---|---|---|
| Site demand | vf_web_page_viewed → download_clicked → download_requested | request/intent, not completed file transfer |
| Instructions | install_help_viewed → install_step_viewed → installation_link_confirmed | successful claim response only, not OS installation |
| First launch | vf_app_first_run_confirmed | new successful first-party acknowledgement with provider consent; no historical backfill |
| Activation | first consenting installation with run_completed or local_conversion_completed, then media_exported | proposed operational definition; no saved governed definition claimed |
| Media outcomes | run_started/completed/failed/stopped and local_conversion equivalents | each real attempt; skipped/stopped/failed remain distinct |
| Feature adoption | vf_app_feature_used(feature,action), playback_started | approved action vocabulary only; no media identity/content |
| Reliability | failure_reason, failure_stage, update_stage, version/os/architecture | enum categories, no exceptions/stacks/private messages |
| Performance | processing_bucket, wait_bucket, output/media duration/size buckets | coarse bins, not exact latency percentiles or paint timing |
| Retention | app_opened or successful export on days1/7/30 per namespace-hashed installation | same consenting installation only; resets/missing consent remain unknown |
| Release adoption | app_opened grouped by app_version/os/architecture | observed consenting installations, not download count/install base |

Recommended dashboard tiles: production release adoption; consenting first launches;
first-launch→first-export funnel (same installation, seven-day window); start→terminal
outcomes by output kind; failure reasons/stages; processing/wait bucket distributions;
approved feature/action adoption; D1/D7/D30 opened/export retention. Save native
PostHog Trends/Funnels/Retention nodes after verifying actual schema. Empty or
unavailable data remains unknown/zero observations, never a pipeline-health pass.
No dashboard, cohort membership or production adoption number was fabricated.

Provider semantics references: https://posthog.com/docs/api/capture and
https://posthog.com/docs/data/events#event-deduplication .
