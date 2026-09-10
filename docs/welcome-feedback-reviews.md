# Welcome, feedback, and ratings

Implemented on the feature branch; not part of the published 0.1.9 app.

## User journeys

- Fresh profiles see the native four-slide welcome tour after the analytics choice
  finishes (or immediately after that stage is bypassed). Existing profiles do not.
  Closing, skipping, or finishing marks it seen; Help can replay it. Its detail
  slider is interactive but changes only the illustrative preview.
- Help & feedback is available in the header and Settings. Feedback has a reason,
  a 2,000-character message, and optional reply email. It does not enable analytics.
- Recent failure diagnostics are optional and unchecked. Review shows the bounded,
  redacted failure context before sending. The canonical public video URL has a
  separate unchecked option. Cookies, credentials, whole logs, local media, and
  arbitrary source URLs are not attached. Review the attachment: redaction is a
  safeguard, not a guarantee that every possible provider message is anonymous.
- A rating is offered once after three distinct successfully completed download
  operations. A playlist counts once; partial, failed, and cancelled operations do
  not count. Prompts wait for idle state and other dialogs to close. Manual rating
  remains available through Help. Names default to Anonymous; comments are optional.
- Ratings explicitly submit public reviews: the form discloses website publication
  of the rating, comment and display name, and the action is Submit public review.
  That action records publication permission; there is no preselected checkbox.
  Server-side moderation still gates publication. Help & feedback remains private.

## Ownership and delivery

Installation/onboarding state owns eligibility and the bounded three-operation
milestone. EngagementUI sequences surfaces; the existing native showcase owns tour
rendering. SupportPanel owns the consent snapshot and protected form layout.
SupportTransport owns explicit delivery using a separate private support credential,
not telemetry enrollment. The existing private JSON primitive is shared without
sharing identity. DownloaderApp only connects terminal outcomes and UI entry points.

The server accepts only a closed, bounded schema. Independent credential ownership,
revocation, edge limiting, atomic daily budgets, and exact idempotency receipts apply.
Failed delivery preserves text; retrying the same payload preserves its request ID.
There is no automatic background upload. Closing the app during an uncertain send
can lose the unsent form; there is deliberately no durable diagnostics queue.

When human verification is required, submitting opens the trusted VODForge browser
check. After completing it, return to the preserved form and submit again. The
browser receives a short-lived one-use challenge, never the report or credential.
Verification alone is not a delivery receipt. Production keys and an authorized
live verification journey are required before activation.

## Activation and evidence

The site migration and support feature flag must be deployed before submissions
work. Missing policy/schema fails closed. No production deployment, D1 migration,
app installation, or release is implied by source tests. See the site repository's
`docs/support-operations.md` for activation, moderation and retention.

Run `tests/test_engagement.py` and `tests/test_support_transport.py` for state,
privacy, and delivery contracts. The required native surface gate also runs
`tests/test_support_native.py`; skips are not accepted as native proof. The site
`test/support.spec.ts` exercises real isolated Worker/D1 writes, ownership races,
consent, quotas, and replay. Packaged macOS/Windows and live endpoint checks remain
separate release evidence.

## Opt-in remote preview journey

Run `VODFORGE_DISABLE_TELEMETRY=1 .venv/bin/python -m
scripts.support_preview_journey --output build/support-preview-journey-<unique-run>
--qa-key build/qa-access-key` with native display/network permission. This is an
explicit remote-write QA command, never an automatic unit test. It refuses any
HTTP target other than the fixed preview support endpoint; SQL uses only preview
D1 `924640fb-3be3-47ca-992c-1c7745bd8469`. Production transport code is unchanged:
the driver substitutes the destination and adds the existing preview admission key.

The driver exercises production native forms, real transport, deployed routes and
direct remote D1 readback. It covers all eight feedback permission combinations,
five reasons, five star values (including lowering five stars), optional names and
comments, anonymous defaults, maximum lengths, invalid/empty forms, cancellation,
exact retries, and real quotas. Response-loss injection occurs only AFTER the real
server commit; retry must match the original request and one durable row. There
are no fabricated success responses. Existing receipt cases can be resumed without
resending them; preview's normal credential/IP/day limits still apply to new runs.

Evidence is written to the run's receipt.json, containing synthetic submitted rows,
not bearer secrets. Review edits share one row per credential, so each version is
read back before the next edit. Test profiles and synthetic preview rows are retained
for inspection; do not mistake these for customer submissions. Never check the
private credentials or preview database export into Git.

This is source-native form-to-remote-D1 evidence, not packaged macOS/Windows proof.
Preview uses its QA access gate with human verification disabled. Real browser
Turnstile completion remains unverified; local verification-provider contract tests
do not replace that live step. Production support remains disabled.
