# Welcome, feedback, and ratings

This covers the first-run welcome, the welcome tour, release announcements, the
support invitation, Support (feedback), public reviews, and privacy requests in
the Qt app.

## First run and announcements

- A fresh profile sees one compact welcome screen after the analytics choice
  settles: "Your videos. Ready when you are." with Get started and an optional
  Follow @VODForge action. Profiles that existed before onboarding state was
  recorded are not treated as first runs. Opening the screen marks the welcome as
  presented, so it appears once. See
  [optional welcome and social invitation](../engineering-quality/ONBOARDING_SOCIAL_INVITATION.md).
- The full six-slide welcome tour is available at any time from **Welcome tour**
  (Help popup) or **Help → Welcome Tour** (menu bar). Its playlist and YouTube
  access examples do not change saved settings.
- What's New and the Did you know? tip appear automatically only when a release
  sets `SHOWCASE_MODE` in `yt_downloader/whats_new.py` to `whats-new` or
  `did-you-know`; each showcase appears once per `SHOWCASE_ID`. The current
  setting is `none`, so neither appears, and the What's new entries are hidden
  (they show only in `whats-new` mode). The Did you know? tip ends with
  **Try it**, which closes it and opens Settings. A fresh profile's welcome marks
  the current showcase as seen.
- Existing users may see one support invitation (Follow @VODForge on X) after
  eight seconds of idle UI, once higher-priority prompts have settled. Not now,
  Escape and Follow all dismiss it permanently. The first-run welcome already
  includes this invitation, so it is not shown again.

## When automatic prompts appear

`Bridge.checkEditorial` (`yt_downloader/qt_quick/main.py`) runs on a 700 ms
timer from `Main.qml` and opens at most one prompt, in this order: first-run
welcome, rating request, release announcement, support invitation. It waits
until all of these hold: the window is active, no text is being edited, no popup
or menu is open, analytics consent has settled, no download is active, busy or
queued, and nothing is playing.

## Entry points

- **Settings** footer: **Support** opens the feedback form; **Help** opens the
  Help popup.
- **Help popup**: Support, Write a review, What's new (only in `whats-new`
  mode), Welcome tour, Request my data, Request data deletion.
- **Menu bar Help menu**: Welcome Tour, What's New (enabled only in `whats-new`
  mode), Contact Support…, Privacy Details. There is no review entry in the
  menu bar.

## Support (feedback)

- A reason (Download problem, Playback problem, Interface problem, Suggestion,
  Other), a message of up to 2,000 characters, and an optional reply email. It
  does not enable analytics.
- **Include recent diagnostics** is unchecked by default and is enabled only when
  a recent failed run left failure context; otherwise the form says no recent
  diagnostics are available. **Review diagnostics** shows the bounded, redacted
  attachment before sending.
- The YouTube source link and the output folder have their own unchecked
  options, shown only when that context exists. The folder is attached only if
  diagnostics are also included. The review view and the sent payload use the
  same attachment projection and include only the selected options.
- A YouTube link is not evidence that a video is public; private or unlisted
  links can identify content. Cookies, credentials, whole logs, local media and
  arbitrary source URLs are never attached. Redaction is a safeguard, not a
  guarantee that every provider message is anonymous.

## Public reviews

- A review request opens once, after three distinct successfully completed
  download operations. A playlist counts once; partial, failed and stopped runs
  do not count. Reviews are always available from **Write a review**.
- One to five stars, an optional comment of up to 1,000 characters, and an
  optional display name of up to 80 characters. A blank name is sent as
  Anonymous.
- The form states that the rating, comment and display name may appear on the
  VODForge website, and the action is **Submit public review**. Submitting
  records publication permission; there is no preselected checkbox. Server-side
  moderation still gates publication. Support messages stay private.

## Privacy requests

**Request my data** and **Request data deletion** use the existing telemetry
credential (they never enroll one) to issue a request, then open the browser to
confirm it. Opening the page deletes nothing, and issuing a request is not proof
of erasure. If privacy requests are unavailable, the privacy page opens directly.
**Privacy Details** opens the privacy page. Both requests work regardless of the
analytics switch.

## Ownership

| Concern | Owner |
| --- | --- |
| Welcome and rating eligibility, the three-operation milestone | `EngagementState` (`yt_downloader/engagement_state.py`), stored in installation state |
| Welcome, tour and announcement rendering | `EditorialPopup.qml` |
| Prompt order and gating | `Bridge.checkEditorial` (`yt_downloader/qt_quick/main.py`) |
| Support and review form, consent controls | Support popup in `yt_downloader/qt_quick/Main.qml` |
| Form session, request IDs, background send | `QtSupportSession` (`yt_downloader/qt_quick/support.py`) |
| Payload validation and limits | `yt_downloader/support_payload.py` |
| Failure context and redaction | `yt_downloader/support_diagnostics.py` |
| Delivery | `SupportTransport` (`yt_downloader/support_transport.py`) |

## Delivery

`SupportTransport` sends only on an explicit submit, using a separate private
support credential, not telemetry enrollment. The server accepts only a closed,
bounded schema, with independent credential ownership, revocation, edge limits,
atomic daily budgets and exact idempotency receipts. A failed send keeps the
text; resubmitting the same payload reuses its request ID, and a changed payload
gets a new one. There is no background upload and no durable queue: closing the
app during an uncertain send can lose the unsent form.

When the server requires human verification, submitting opens the trusted
VODForge browser check. After completing it, return to the preserved form and
submit again. The browser receives a short-lived one-use challenge, never the
report or credential. Verification alone is not a delivery receipt.

The site's support migration and feature flag must be deployed before
submissions work; missing policy or schema fails closed. See the site
repository's `docs/support-operations.md` for activation, moderation and
retention.

## Tests

- `tests/test_engagement.py`: first-run eligibility, the three-operation
  milestone, diagnostics redaction and the public-link rule.
- `tests/test_support_payload.py`: consent options, payload validation and the `QtSupportSession` request identity.
- `tests/test_support_transport.py`: delivery, credentials, verification and
  retries.
- `tests/test_whats_new.py` and `tests/test_qt_whats_new.py`: showcase catalog
  and editorial prompts.
- `tests/test_qt_scene_port.py`, `tests/test_qt_interaction_invariants.py` and
  `tests/test_qt_popup_toggle_order.py`: the support popup and Help entry points
  in the Qt scene.

The site's `test/support.spec.ts` covers Worker/D1 writes, ownership races,
consent, quotas and replay. Packaged macOS/Windows and live endpoint checks are
separate release evidence. The removed remote preview journey is described in
[history/support-preview-journey.md](history/support-preview-journey.md).
