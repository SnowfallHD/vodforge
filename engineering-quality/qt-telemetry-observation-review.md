# Qt observation owners and renderer applicability

This change supplies the 18 supported Qt observations identified by the Oct 11
source-owner review. It observes existing admitted actions or actual presentation;
it does not create test events in production, change schema v2, or add user content.

| Observation | Actual owner/callback | Focused evidence |
| --- | --- | --- |
| Archive inspector, paging, sorting, version and volume selection | Accepted Bridge navigation and shared browser/storage changes, including the folder inspector | `test_archive_observations_follow_admitted_changes`, `test_folder_inspector_observes_actual_selection_and_version_change` |
| Relink cancel requested | First request while the actual QtRelinkSession commit remains working; final cancelled state still comes from settlement | `test_relink_cancellation_observes_request_once_and_actual_cancelled_outcome` |
| Help dispatched and lifecycle | Qt menu onOpened/onClosed, actual support/editorial admission and visible panel callback; actual support replacement | `test_help_dispatch_retains_original_consent_and_actual_panel_lifecycle`, `test_rendered_qt_menu_selection_search_and_help_use_real_callbacks` |
| Library menu, search focus and selection start/finish | Existing QML opened/focus and admitted selection callbacks | `test_rendered_qt_menu_selection_search_and_help_use_real_callbacks` |
| Player hover shown/unavailable | QtPreviewSession result with its original consent context, followed by actual visible QML image readiness or unavailable state | `test_preview_observation_requires_current_visible_result_and_original_consent`, `test_real_qml_hover_callback_waits_for_visible_ready_frame` |
| Player related shown | Rendered related cards and an exact live playback owner | `test_rendered_related_observation_requires_actual_cards_and_live_owner` |
| Watch catalog/rail scroll, stale detail intent and search focus | Actual input movement, rejected detail owner and existing focus callback; layout restoration emits nothing | `test_rendered_watch_scroll_reports_input_movement_not_layout_restoration`, `test_retired_watch_detail_intent_is_observed_without_private_owner` |

Delayed Help and hover observations cannot adopt a revoked, regranted or initially
denied consent context. Replaced hover work cannot publish for another media item;
no hover event is recorded merely because a worker returned. Sink failure leaves
user operations unchanged. Local outbox controls assert that titles, URLs, media
paths, messages and private owner values never reach public payloads.

The focused QtHelpObservations owner tracks observation correlation only. Existing
support/editorial owners retain UI state and behavior. ProductTelemetry retains
consent, event persistence, dedupe and delivery; its extracted consent-context helper
is shared by operation and feature bindings. Bridge forwards actual existing
admission/presentation callbacks. No responsibility was added to app.py. Legacy
renderer-specific behavior remains explicitly documented rather than emulated.

## Actual legacy semantics

A nonempty set of verified Qt launch attestations excludes these seven pairs:

- `help_operation/popup_returned`: synchronous Tk popup/grab return.
- `library/source_tags_copied`: original source tags, distinct from personal tags.
- `library/thumbnail_url_copied`: Qt exposes no corresponding URL-copy action.
- `playback_operation/focused`: focusing an existing player, whereas Qt replaces it.
- `player/description_opened` and `description_closed`: Tk expand/collapse; Qt displays description directly.
- `watch/singleton_shown`: the dedicated lone-episode Tk layout; Qt uses its generic hero/catalog presentation.

Qt Help replacement and shared download reuse remain required. Unknown, unverified
and mixed renderers retain legacy requirements. The shared vocabulary remains 215
pairs; verified Qt requires 207 including the existing Mac-controls-fallback
exclusion. Native ordering, privacy, operation correlation and candidate binding
remain strict. Source applicability controls previously failed 14 verified-Qt cases
and now pass all 120 cases, including shared/Qt actions that must remain required.

## Windows evidence portability

Static-analysis stdout/stderr files now retain original newline bytes instead of
Windows text translation. The evaluator still rejects a translated log even when
its hash is recomputed. Recorded roots and keys use both POSIX and Windows path
semantics independent of the evaluating host; drive-relative and traversing keys
remain rejected. Prior-failure controls demonstrate the original POSIX-root failure
and two cross-host invalid-key acceptance cases. Artifact containment, source
hashes and original stdout identity checks remain unchanged.

## Retained evidence and limits

The task retains before/after logs and JUnit reports under
`task/release-completion-20261010/`: `evidence-portability-before`,
`qt-observations-before-corrected`, `qt-routes-before`,
`qt-legacy-applicability-before`, `source-key-before`,
`affected-telemetry-final`, `affected-source-contract-final`,
`affected-library-route-final` and `watch-wheel-existing-control`.
The corrected rendering fixture targets visible controls and uses the actual
player overlay visibility contract; its initial failures are retained as fixture
failures, not attributed to product behavior.

These source-tier controls do not prove signed native presentation or remote D1
observations. Runtime bytes changed, requiring one successor signed candidate and
only affected/build-dependent native evidence before publication. Previously
completed moves, pause/resume, restart, memory/process and Update/Repair behavior
checks remain closed. Existing failed/finalized native wrappers remain preserved.
Mac foreground and production D1 were untouched by this work.
