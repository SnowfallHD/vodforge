# Support preview journey (removed)

This records the opt-in remote QA driver `scripts/support_preview_journey.py`,
used for the 0.2.0 Support and public-review work. It drove the Tk support forms
through real transport to the preview support endpoint and read results back
from the preview D1 database. The script and its native form test
(`tests/test_support_native.py`) were removed with the Tk interface in October
2026. Current support behavior and tests are described in
[welcome-feedback-reviews.md](../welcome-feedback-reviews.md).

## How it ran

`VODFORGE_DISABLE_TELEMETRY=1 .venv/bin/python -m scripts.support_preview_journey
--output build/support-preview-journey-<unique-run> --qa-key build/qa-access-key`,
with native display and network permission. It was an explicit remote-write QA
command, never an automatic unit test. It refused any HTTP target other than the
fixed preview support endpoint, and its SQL used only the preview D1 database
`924640fb-3be3-47ca-992c-1c7745bd8469`. Production transport code was unchanged:
the driver substituted the destination and added the existing preview admission
key.

## What it covered

The driver used the production native forms, real transport, deployed routes and
direct remote D1 readback. It covered all eight feedback permission combinations,
five reasons, five star values (including lowering five stars), optional names and
comments, Anonymous defaults, maximum lengths, invalid and empty forms,
cancellation, exact retries and real quotas. Response loss was injected only after
the real server commit; the retry had to match the original request and one
durable row. There were no fabricated success responses. Existing receipt cases
could be resumed without resending them; preview's normal credential, IP and
daily limits still applied to new runs.

Evidence went to the run's `receipt.json`, containing synthetic submitted rows,
not bearer secrets. Review edits shared one row per credential, so each version
was read back before the next edit. Test profiles and synthetic preview rows were
kept for inspection and were not customer submissions. Private credentials and
preview database exports were never checked into Git.

## Limits

This was source-native form-to-remote-D1 evidence, not packaged macOS or Windows
proof. Preview used its QA access gate with human verification disabled, so real
browser Turnstile completion was not exercised there. A later 0.2.0 production
check completed real Turnstile verification, then submitted synthetic feedback
and a private review over HTTPS. Direct D1 readback confirmed exact retry
receipts, Anonymous normalization and pending moderation. The test content was
removed and its credential revoked. That was live service proof, not packaged
native-form proof.
