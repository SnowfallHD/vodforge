# Telemetry metric contract audit — September 11, 2026

## Findings and fixes

- **Last seen:** `installations.last_seen_at` is a server-observed app launch time,
  not a heartbeat and not a derived latest-event time. The desktop mistakenly
  reused its durable per-version launch receipt to suppress future session pings.
  Session observation is now in-memory on the existing attribution/credential
  owners; successful enrollment/version authorization remains durable. Startup and
  later consent grant use the existing delivery coordinator. Failed requests remain
  retryable without creating another identity or claiming successful observation.
- **Original audio:** the desktop intentionally emits null `output_type` because
  schema v1 has only MP4/MP3. The enrolled server's plausibility check incorrectly
  rejected those lifecycle/playback events. Null format is now permitted for these
  existing events; invalid combinations and enums remain rejected. No migration
  or fabricated MP3 classification is introduced.
- The production 30-day discrepancy was 27 event-active installations versus 9
  launch observations; 18 legacy 0.1.8 installations had null last-seen values.
  That read-only diagnosis predates these changes. Historical null observations
  are not backfilled with invented launches. Events do not prove a particular
  app-open timestamp. A session spanning a reporting boundary can legitimately
  have newer events than its last launch; document the metric as a launch signal.

## Metric inventory and owned contracts

| Metric | Source and intended meaning | Required coverage |
| --- | --- | --- |
| Users/new users | One installations row; created_at is first recorded, not people or necessarily launch | Fresh enrollment, concurrent/exact retry, credential ownership, source filters |
| First launch | First authenticated launch, immutable | Fresh launch, same-version reopen, upgrade |
| Last seen | Each consent-enabled app session launch, server time | Two persisted sessions, failed retry, unknown/denied/off suppression |
| Current version | Latest enabled server-ordered observed running version | Upgrade, repeat, old delayed launch, invalid release |
| Updates | One client_update per forward observed version transition | Correct from/to, no same-version duplicate, no rollback |
| Active/daily/weekly/returning | Distinct installations with selected-channel events; returning uses two UTC dates | All event names stored once, UTC period/dedup/filter semantics; not a per-run success rate |
| App opens | One app_opened per permitted process session | Repeat callbacks, restart, consent grant/withdrawal |
| Run starts | Actual worker start, not mere queue submission | MP4, MP3, Original; queued promotion |
| Completion/failure/stop | Terminal attempt outcome; partial maps to completion under current contract | Exact attempt dedup, controlled failure/retry, cancellation; bounded failure facts |
| Formats/features | Recorded output_type/run_kind on events | MP4/MP3 plus intentionally unlabeled Original, local conversion |
| Playback | Actual playback-start callback | MP4/MP3/Original, no click-only success |
| Local conversion | Successfully recorded local MP4 conversion | Valid output/history, one completion event |
| Settings/Cloud interest | First Settings impression / first Cloud action | Authenticated cloud_seen/cloud_click, immutable first-observed values, consent |
| Source/browser links | Permission-owned attribution claim and installations.source | Claim-before-enrollment, accepted/refused/browser-unavailable, immutable identity |
| Downloads/source | Website download requests, not installed people | Actual supported asset/ref validation and request dedup policy |
| Waitlist | Explicit website signup, separate from optional product events | Existing website validation/identity/consent contracts |
| Feedback/reviews | Explicit support submissions; independent of optional analytics | Separate support test suite, retry receipts, moderation/privacy, not inferred from product activity |

The required backend suite covers ingestion/authentication, rate admission,
revocation, ownership, source attribution, browser permission, downloads, waitlist,
and support. The cross-repository local contract uses real Python serialization,
HTTP, the production Worker handlers and migrated local D1 for all product event
names/dimensions, exact retries, launch observations, version changes and Cloud
observations. The packaged preview gate adds actual UI producer-to-remote-D1 proof
on both shipping platforms; local tests alone do not establish that tier.

No telemetry consent defaults, production database records, user profiles, or
third-party provider permissions are changed by this audit. See
[the required release journey](../engineering-quality/TELEMETRY_RELEASE_GATE.md).

## Verification recorded in this lane

- Server source `04352c1`: all 117 site tests pass; preview deployment
  `76515cef-d83c-4880-ac47-a02e661f1ce7`, migrations through 0014. Production site
  and production D1 remain unchanged by this lane.
- Real local HTTP/Worker/D1 all-event contract passes. The retained earlier failed
  attempts exposed an incorrect test expectation for duplicate acceptance and
  timestamp string formatting; final checks compare the same instant at the
  server's documented millisecond precision rather than weakening event identity.
- Private production-policy Mac package from runtime source `cdb37bf` passes bundled
  smoke and two actual app launches against preview D1: one credential, two app-open
  events, increased last seen, unchanged first launch, no update event. Two further
  actual launches with denied consent and the off switch leave D1 unchanged.
  This is an ad-hoc private artifact, not final signed-release certification.
- Windows source regressions at `cdb37bf`: 115 pass. CRM's 12 query/auth/filter tests
  pass. Required Mac native gate now includes consent UI: 101 pass. Native test
  setup drains its first Tk root's pending show callback; it previously crashed
  between roots, causing a subsequent macOS Python restoration prompt. No product
  UI workaround or saved macOS preference change was introduced.
- New app-producer tests additionally cover actual worker-launch emission,
  completion/partial/failure/stop mapping, Original playback, shutdown suppression,
  and local conversion after canonical history registration.
- These are distinct proof tiers. No new release was requested or published. The
  next public release must pass the new all-action signed-artifact preview journeys
  on both platforms; this audit does not relabel startup-only or source tests as
  that completed release gate. Detailed receipts remain in
  `build/telemetry-session-gate/`.
