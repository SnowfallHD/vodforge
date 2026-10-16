# Desktop analytics contract, schema 2

This successor changes runtime code and needs a new immutable private candidate. The earlier signed 0.2.6 packages and their checksums remain preserved; their approval does not cover successor bytes. Planned package version remains 0.2.6 for existing released-version admission, with a distinct source SHA, output directory, executable and archive hashes. No ordinary app replacement, upload or public publication is implied by private qualification.

## Identity and traffic classification

Project 664300, US ingestion; `surface=desktop`, `schema_version='2'`, `environment=production` (ingestion environment), `app_version`, `os`, `architecture`, existing `release_channel=production|development|test`. Preserve this existing channel taxonomy rather than renaming production to stable. Default `measurement_scope=production`; `is_test` is true for nonproduction channels. An explicitly supplied valid UUID4 `VODFORGE_POSTHOG_QA_RUN` makes provider traffic `release_channel=test`, `measurement_scope=qa`, `is_test=true`, with `qa_run_id` and `validation_id` equal to that controlled label. The original channel becomes `build_release_channel`. Invalid nonempty QA labels disable the configured provider. This label never grants consent or enables telemetry.

Dashboard exclusion: `is_test=true OR measurement_scope=qa OR release_channel=test`, also excluding historical test events without new fields. Controlled QA is technical verification, never adoption. Installation distinct ID is `vf_install_` + SHA256(`vodforge:posthog:installation:` + installation UUID); raw installation IDs never enter PostHog. Website identity remains separate. No alias or guessed browser-to-install/person/cross-device join. Person profiles off, IP override0.0.0.0/GeoIP off. Transport still necessarily reaches the configured provider.

Those QA properties apply to the provider projection, not the first-party D1 envelope. The two controlled production runs on October15 created30 D1 rows still labeled `release_channel=production`. All30 UUIDs and event/feature/action metadata match the retained QA receipts exactly. Their exact-ID anti-join is recorded in `build/posthog-comprehensive-20261015/source/first-party-qa-reconciliation/exclude-owned-qa.sql`; health/adoption queries must apply it without deleting or relabeling rows. Never exclude an entire version, platform or time window. Before another production QA run, register exact event exclusions with the first-party health owner, or implement and verify a supported first-party QA-marker contract. Provider QA filtering alone cannot qualify first-party metrics.

$screen and $exception companions have distinct deterministic UUID5s derived from the custom event UUID; retries reuse those IDs.

Provider-only context: `$session_id` UUIDv7, `event_sequence` bounded integer, `session_elapsed_ms` in100ms steps capped24h. Session identity starts per process/provider-consent epoch and changes on revocation/reenrollment; old queued events retain their admitted context. These local outbox fields never enter the first-party event envelope. Existing hashed UUID5 `attempt_id`/`retry_of` and approved operation UUID/step link process events. All closed dimension enums are projected; raw/arbitrary dimensions are discarded. Build revision is only a40hex build-time SHA.

## Events and measurement

Existing names retained: `vf_app_app_opened`, `vf_app_run_started/completed/failed/stopped/queued/dequeued/skipped`, `vf_app_local_conversion_started/completed/failed/stopped`, `vf_app_playback_started`, `vf_app_media_exported`, `vf_app_feature_used`. Meaningful feature actions use the existing closed vocabulary, including navigation, download processing, playback, file operations, retry, recovery and update stages. Processing/wait/media-size/duration are existing coarse bins; unknowns remain absent. Failures expose approved reason/stage/code only.

`vf_app_first_run_confirmed` is emitted only after a newly successful canonical first-launch acknowledgement with retained provider permission. No historical backfill. `app_opened` is per app launch with permission. Activation can be analyzed as first successful `media_exported` per consenting installation, or first-run→completed core operation→export funnel; this is an operational definition, not a completed download or OS-install claim. Same-install D1/D7/D30 retention uses later app_opened/export events. User preference/identity resets leave continuity unknown.

Additive `vf_app_feature_used`, `feature=application_lifecycle`: `session_started`, `session_ended`, `startup_ready`, `unclean_previous_exit`, `unhandled_exception`, `heartbeat` (at most every5minutes), `foreground`, `background`, `screen_viewed`. The view is exactly forge/library/watch/activity, and each real view transition plus the initial current view emits a canonical event and a standard `$screen` companion with `$screen_name`. Both are the same observation; do not sum them. Duration uses `under_10s|under_1m|under_5m|under_30m|under_2h|2h_plus`. Startup_ready is initialization/event-loop readiness with policy wait, NOT first-painted-frame latency. Session end is best effort during normal closure. An owned marker from a confirmed dead process indicates unclean exit; it cannot distinguish crash, force quit, OS termination or power loss. Live/unreadable owners and changed consent epochs are never labeled crashes. Markers contain local PID/create time/consent epochs only, bounded32; no file/media identifiers.

Unhandled exceptions require `exception_kind=type_error|value_error|os_error|runtime_error|memory_error|other` and `exception_origin=main_thread|worker_thread|qt_callback`. Other lifecycle actions forbid these fields. Hook capture chains existing Python/thread hooks and restores only its own hooks; SystemExit/KeyboardInterrupt excluded. One report per kind/origin per process. `$exception` is a companion issue view of the SAME lifecycle exception, not a second failure: static type/value/fingerprint, empty stack frames, no message, traceback, locals, filename, command, source URL, credentials or media. OS/native crashes are not automatically captured; next-launch unclean markers are a limited alternative.

## Native replay and delivery limitations

Actual app is PySide6 Qt Quick/QML, with no browser DOM. Live documentation also lists Unity alongside web JavaScript, React Native, iOS, Android and Flutter; no Qt/Python recorder was found. This is a documentation finding, not an exhaustive vendor capability guarantee. This implementation provides a supported event/semantic session timeline, NOT visual replay, screenshots, audio/video, accessibility-tree capture or a synthetic recording. References: https://posthog.com/pocket-guides/session-replay/configure-replays and https://posthog.com/docs/data/sessions . Manual sanitized exception API: https://posthog.com/docs/error-tracking/installation/manual .

The existing durable first-party queue remains authoritative. Independent provider delivery reuses that outbox with stable top-level UUIDs and persisted exponential retry (30seconds up to1hour), capped by the existing30-day event lifetime and256-event capacity. Custom acknowledgements are retained and never resent merely because the provider failed; provider backlog does not block later custom delivery. Capacity may retire the oldest already-custom-acknowledged provider item with an explicit local diagnostic so a provider outage cannot prevent custom admission. Newly acknowledged first launches also retain a provider-only durable mirror; they never repost the canonical first-launch acknowledgement. Withdrawal/changed provider epochs discard pending old-provider events. Older already-settled mirrors are not backfilled. Canonical acknowledgement does not mean provider ingestion; actual labeled packaged-app readback is required. Network/blocked-policy/withdrawal/offline sessions can be absent. No full raw logging or replay SDK is enabled. Survey/feature-flag/experiment rollouts require a concrete product purpose and do not justify arbitrary remote settings. Separate dashboard reviewer owns saved analytics; this lane writes no dashboards.

First-party additive validator must be deployed before the candidate sends lifecycle feature actions. Website contract: `/Users/coop/Dev/vodforge-site/docs/posthog-comprehensive-contract.md`. Regional provider defaults use only a fresh resolved=true response with both mode=default-on and posthog_mode=default-on from the parent-reviewed US/CH/AU policy. Policy metadata version2 refreshes old generic cache without clearing choices. Missing/unknown provider policy stays opt-in; all explicit refusals override defaults. No desktop replay default is relevant because no native replay is supported.

## Bounded replay investigation and actual production proof

The ignored synthetic investigation at `build/posthog-comprehensive-20261015/replay-investigation/report.md` demonstrates both semantic and Qt-JPEG streams in the actual installed rrweb player, plus a separate-storage viewer. Thirteen fail-closed cases and private-value pixel-invariance/negative controls pass. These are public-only mirrors, not original VODForge window captures. No provider recording was uploaded, no storage provisioned, and PostHog ingestion/UI playback remains unproved. Native original-window/GPU/dialog privacy and supported import decisions remain necessary before rollout.

The signed/notarized dc4c610 ARM candidate ran offscreen with a fictional explicitly consented profile. Exact QA label `62f703a9-a27f-42b7-ba9e-be2f7dbe929e` produced15 canonical D1 events matching15 provider UUIDs exactly once, plus three provider-only rows (first-run mirror, screen, exception), all18 in one session. Provider exception has an issue ID and empty stack frames. The denied fixture refused delivery and an independent exact-label provider query returned zero rows. Receipts are under `build/posthog-comprehensive-20261015/dc4c610/arm64/`. These prove bounded production transport for this real frozen app, not adoption, media activation, physical native consent or all event vocabulary.

Historical Qt source f37eb71 (September23) retained a non-opening attribution adapter and omitted the Tk automatic welcome/ticket handoff. September3 source74ec786 automatically opened a claim URL; September7 source3cd7aa6 moved automatic opening into AnalyticsStartup's ticket welcome while delaying ticket authorization for app consent. Public0.2.5 source850e19e still contains that Tk code, but the maintained Qt entry does not use it. These are inspected source facts, not a verified historical production automatic-completion journey. The later manual914 fixture proved actual canonical browser/app confirmation, but introduced a manual prerequisite the user did not want.

## Later local attribution adapter successor

The user explicitly superseded the non-opening restriction on October15. The current local successor automatically prepares a short-lived operational capability on a worker and opens the default browser on Qt's GUI owner, once per new eligible installation. Persisted attempt admission prevents repeat openings after failed dispatch or cold restart; Settings retains an explicit recovery action. Already-opened pending capabilities can poll on restart without reopening. Completed/migrated profiles do not automatically open another page. Cancellation, build-policy disablement and replacement capabilities remain guarded. No claimed flags are manufactured.

Browser attribution and app usage are independent: app usage Off prevents first-launch usage enrollment/events/provider delivery but does not prohibit the browser-owned operational handshake. Claim confirmation cannot turn usage On. The website must require its applicable browser permission and a retained eligible referral before persisting attribution. A shared campaign label is nonunique source context, not a browser/visitor identifier; the app never reads browser cookies, raw referral context or campaign labels and creates no provider alias. No eligible context or browser refusal means no successful attribution. Operational ticket issue/status state must remain short-lived and must not create a canonical installation/acquisition record before eligibility. This requires the coordinated site staging/no-source correction; do not qualify or run new production automatic-flow QA before that backend is deployed and QA exclusions are registered. Existing custom D1 event names remain intact.

Actual914 manual-journey acceptance and its denied cold-label failure remain immutable evidence. The cold-label source repair presents saved confirmation regardless of current action/usage permission, without sending anything or granting consent. New automatic-flow source, mocks and rendering checks are not signed successor or live automatic acceptance. Original old-profile browser evidence is not original acquisition continuity or binary delivery proof.


### Ordinary QA transport default — October15 correction

The earlier three explicitly authorized comprehensive/live fixtures exercised production D1 and PostHog; provider labels did not route or classify first-party events. This was an intentional endpoint choice for the requested deployed dual-pipeline proof, not a preview-key bypass. Missing preregistered D1 exclusions for the first two was a classification error; external health mappings were also insufficient for the central CRM owner. Site owner now owns exact central exclusions; Cooper personally deleted three QA installation rows, so this lane must not repeat deletion or launch more production QA.

Local successor policy treats existing QUALITY_E2E, QA_PREVIEW_TELEMETRY, QA_PROFILE and POSTHOG_QA_RUN/HOME markers as QA. They cannot fall through to production even in a production-marked frozen app. Existing explicit preview routing still requires its bounded key/profile and mode flags; missing prerequisites mean OFF. Ordinary marked QA/preview also disables production PostHog ingestion; labels alone are not transport approval. No new production override or provider project/settings change is introduced. Production release behavior without QA markers is unchanged. Disabled transport still presents existing local link facts without creating a fresh identity or sending a request. Prior production receipts remain historical, not instructions to repeat their environment.

## Unified app control — 2026-10-15

Cooper's current app UI uses one **Share usage analytics** On/Off control for
first-party and provider analytics. There is no separate provider switch or
installation-association status/control in Settings or onboarding. The privacy
policy continues to disclose the processor; internal identifiers are unchanged.
A new explicit On/Off atomically saves both preferences. At Qt startup, any
historical explicit refusal conservatively migrates both preferences to denied;
migration never grants consent. Missing choices continue through the existing
regional-default checks, with no expansion of default-on coverage. Provider/build
availability remains an internal capability restriction. Failed preference saves
disable the session's collection and report Off, with the existing save warning.
Automatic browser-owned attribution remains independent of app usage permission;
no automatic operational request is evidence of consent or a successful link.

## Coarse native baseline, separately resolved — 2026-10-16UTC

The existing product telemetry worker now also admits five coarse first-party
count metrics: app_started, run_completed, run_failed,
local_conversion_completed, local_conversion_failed. This path is independent
of optional detailed sharing, but requires a fresh positive feature-specific
policy response (native_baseline_mode=enabled, native_baseline_version=1,
resolved=true), the existing build/QA transport boundary, and no historical
broad refusal lacking the current usage_scope_version. New explicit On/Off
saves that scope marker; migration never manufactures it. Identical regional
eligibility gives default-Off and new manual-Off the same coarse fields. A
historical broad denial remains the explicitly stricter compatibility case.

The server owner independently assesses US/CH/AU for these first-party,
non-content counts; UK/EEA/other/unknown modes remain disabled for this new
phone-home. This is not inherited from the website replay matrix and not a
universal legal-clearance claim. The server independently enforces its region,
signals, feature flag and registered-version checks. Existing rich default
coverage remains unchanged; cached rich consent policy still works on outage,
while no cached/default mode substitutes for fresh baseline eligibility.

POST /api/telemetry/baseline contains exactly schema_version, platform,
app_version, metric, count(1..100). No credentials, installation/browser/session
IDs, individual event timestamp, source, media data, failure content, operation
ID or extra dimensions. It is not mirrored to PostHog. Counts are bounded in
memory, sent once, never persisted or automatically retried after an ambiguous
result; loss/repeated process launches/producer callbacks prevent unique-user,
unique-install, complete-run or exactly-once claims. app_started means a process
observation, not activation. Positive policy expires after24hours in memory;
new processes resolve again. No extra fresh UUID is generated for counts.

Matching server contract aggregates by UTCday/platform/version/metric with
30UTCday retention; separate security processing can use IP and daily keyed
rate-limit hashes. Request headers/network metadata still reach the service;
no assertion of anonymous transport, no processing of arbitrary bodies for
measurement. Existing local UUID, installation facts and optional outbox remain
owned by their existing functionality. Optional Off still revokes/blocks rich
first-party/provider events and queues; desktop replay is absent in every mode.
Backend deployment and exact packaged/native verification are separate gates;
source/intercepted tests do not certify activation or production delivery.
