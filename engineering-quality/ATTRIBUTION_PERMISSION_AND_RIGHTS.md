# Attribution permission and privacy requests

Private successor to 8159164; public 0.2.5 is unchanged. This is a source/test contract, not a deployment, deletion-completion, or native-package receipt.

## Earliest attribution boundary

The app requires permission BEFORE issuing a claim containing an installation UUID and a random capability. Browser consent at consume cannot authorize an earlier app transmission. Generic first-party mode, PostHog mode, baseline permission, existing installation identity and old grants are not substitutes.

The existing identifier-free policy lookup may return `attribution_mode: "default-on" | "opt-in"`, `attribution_policy_version: 1`, and `resolved: true`. The server owns the user-selected US/CH/AU default-on policy; the app requires these exact positive fields. Default permission is process-local, expires after 24 hours, is cleared on refresh/failure, and is never recovered from the older generic policy cache. Every new process must resolve anew. A legacy explicit grant does not acknowledge the new attribution scope. A new explicit unified On stores `attribution_permission_version: 1` atomically with the two optional-sharing preferences; Off denies the handoff irrespective of region. Migration does not manufacture acknowledgment. Local functional UUID retention is unchanged.

New issues add `attribution_permission_version: 1` and `attribution_choice: "default" | "granted"` alongside existing `install_id` and `claim_token`. These are permission assertions, not proof of a human, official binary or completed download. No referral/content fields are introduced.

The low-level issue/status transport defaults to denied and requires an operation permission callback. The shared owner checks permission before issuing, before persisting its result, before browser dispatch, before status requests and before committing confirmation. A permission epoch/policy generation fences Off→On and policy replacement so stale work cannot become newly authorized. In-flight requests cannot be recalled; Off does not delete existing remote records or undo a completed association.

Blocked automatic admission does not set the one-time attempt bit. On later opt-in, the existing automatic path can run without a manual Link button. The bit is taken at permitted request admission; actual attempted network failures still count as an attempt, preventing repeated automatic browser activity. Existing-profile eligibility and confirmed/opened-capability safeguards remain. No PostHog/provider or linked-status control is added.

## Rights action protocol

Help exposes **Request my data** and **Request data deletion**. Opening a page does not mean data was erased. These explicit actions are independent of optional analytics On/Off.

A fresh policy capability `privacy_requests_version: 1` is required before the app uses the new route. Missing/old/failed policy falls back to the public Privacy page. The client reads only an existing bounded private telemetry credential; it never creates a credential, enrolls an installation or enables analytics to request rights. No credential means public Privacy help. It does not display the raw installation UUID.

Agreed issue request: `POST /api/privacy/requests/issue`, existing bearer secret, exactly `{schema_version:1, credential_id, request_kind:"access"|"deletion"}`. No redirects are followed with the ownership secret. Valid response: schema1, matching kind, random UUID request receipt, state `awaiting_confirmation`, fixed HTTPS canonical `/privacy/request/#token=<43-character random capability>` and a future expiry no more than 16 minutes away (server target 15 minutes). Token remains in memory/URL fragment; it is not logged, persisted by the app or sent to an analytics provider. QA transport continues to use its existing preview route; no production fallback is added.

Browser confirmation is separate and queues a request. Backend ownership, inspect/confirm, state progression and actual processing belong to the website lane. Proposed states distinguish awaiting_confirmation, requested, first_party_completed, provider_pending, completed, unsupported and expired. `completed` must require verified provider erasure including personless events; deleting a person profile is insufficient proof. No actual deletion, provider access, new credential, vendor contact or production request is authorized/performed by this change. Client routing stays unavailable until the deployed capability is present. Server implementation/deployment and end-to-end acceptance are still dependent gates.

Provider runbook identity, source `posthog_analytics.installation_distinct_id`:

`"vf_install_" + SHA256(UTF8("vodforge:posthog:installation:" + exact_stored_install_id)).hexdigest()`

The hex is lowercase, 64 characters. The helper performs no stripping, case folding or UUID normalization; use the exact stored representation. No actual identity or secret is included here. Existing app Help→Support uses `/api/support/`; public help is `https://getvodforge.com/privacy/`. No support email was verified.

## Proposed full public wording

“Share usage analytics controls optional app reports and referral association. Turning it Off stops new optional reports and attribution requests; it does not erase information already received. For new installations without a saved choice, referral requests may start by default only after a fresh policy resolves to the United States, Switzerland or Australia. Elsewhere, or if the policy is unknown, a current explicit choice is required. The browser separately requires its own permission and an eligible saved referral before linking. Regional basic operation totals and service/security records are separate. Use Help → Request my data or Request data deletion to start a privacy request. Browser confirmation and verified processing are required; opening the request is not confirmation that deletion is complete.”

Short app disclosure retains Privacy details and does not assert a legal exemption, global anonymity, universal network silence, historical deletion or public release completion.

## Bug-class learning and evidence

Previous tests intentionally proved browser attribution was independent of optional app usage and tested the final browser consent/consume boundary. They missed the earlier installation-ID/capability request. The corrected invariant is authorization before the first sensitive transmission, preserved across issue/persistence/dispatch/poll/ack and permission replacement. Existing independent-while-Off expectations are explicitly superseded, not silently skipped.

Three actual owner regressions reproduce issuer invocation with no relevant permission before the fix; the remaining initial cases expose the absent policy/ack API. Original 10-failure log and intermediate failures are retained under `build/privacy-attribution-20261016/`. Cross-owner coverage includes old/new permission, fresh/expired/offline policy, malformed version, manual denial, Off/regrant and policy replacement, blocked automatic admission followed by opt-in, existing-profile/once-only behavior, polling cancellation/replaced capabilities, failed save/build/closed fences, basic-count parity, existing-credential/no-enrollment rights admission, strict response/expiry/origin, no redirects, GUI-thread dispatch and actual QML Help clicks/one-switch geometry. No broad campaign or prior Trash/native acceptance is repeated or relabeled.

Limits: fake transports and offscreen QML exercise source contracts; no new signed package, native desktop, live backend, provider erasure or network-silence acceptance is claimed. The existing baseline contract and retained historical broad refusals remain unchanged. Exact final test counts are in the change/test log.
