# Bounded candidate input trace

`yt_downloader.qt_quick.input_trace.InputTrace` is opt-in, local-only diagnostic
code. Importing it changes nothing. It is not enabled in product startup, wired
to telemetry, injected into another process, or automatically written to disk.
Use only in an explicitly isolated source candidate launcher. A frozen candidate
must include the module through its own launcher/build; the running signed
release cannot acquire this observer without a new candidate process.

## Minimal hook for the owner's isolated launcher

After the candidate's root window is created, and after the launcher has verified
its disposable profile, construct the observer. Keep it alive until export:

```python
from PySide6.QtCore import QObject
from yt_downloader.qt_quick.input_trace import InputTrace

trace = InputTrace(window, max_records=256, seconds=60)
trace.watch_action(window.findChild(QObject, "librarySelectButton"), "library_select")
trace.watch_action(window.findChild(QObject, "libraryFilterButton"), "library_filter")
trace.watch_action(window.findChild(QObject, "headerSettingsButton"), "settings")
trace.watch_popup(window.findChild(QObject, "libraryFilterPopup"), "library_filter")
trace.watch_popup(window.findChild(QObject, "downloadSettingsPopup"), "settings")
# Exercise the bounded native fixture journey, then explicitly export locally:
trace.stop()
receipt = trace.snapshot()
# The isolated launcher may json.dump(receipt, its private evidence file).
```

The example must bracket actual user/test interactions, not immediately stop
before them. Stop before destroying the window/engine. The caller owns candidate
identity, profile isolation, evidence destination and screenshot provenance.
Fixed roles additionally cover Forge Options, Watch More and the four navigation
actions. Repeater delegates must be resolved through the actual visual tree.
Do not resolve dynamic controls by serializing media labels. Registration rejects
unknown roles, duplicate actions, stopped observers and actions on other windows.

## What is captured

- `window_delivery`: pointer press, release, double press, held motion sampled
  at most every 50ms, and window activation/cancellation events.
- `target_delivery`: event delivered to a registered action's existing input
  items. These use QObject event filters, not extra MouseArea signal handlers.
- `action`: existing `activated` emission, separately from event delivery.
- `focus_changed`, popup visibility changes, and deferred `settled` checkpoints.
- At each observation: local pointer position, geometric input candidates in
  approximate paint order with clipping, target bounds/visibility/enabled state,
  current Qt mouse grabber, active focus, popup visible/modal/opacity state.

Item identities are ephemeral opaque tokens and fixed diagnostic action roles.
No objectName, label, accessible name, text, key text, URL, path, media record,
raw pointer address or screenshot is serialized. No key events are collected.
`gesture` is the most recent pointer gesture counter, not proof that a later
keyboard/accessibility/programmatic action came from that pointer gesture.
The event's `spontaneous` flag does not prove physical input: Qt test input can
also be spontaneous. Bind receipts to the actual input method separately.

Default capture stops and disconnects after 256 records or 60 seconds. Hard
configuration limits are 2048 records and 300 seconds. Scene inspection is capped
at 2048 visited nodes, depth 48 and 12 geometric candidates. A truncated scan is
marked. The observer always returns false and never sets focus or grabs input.
It does not connect `MouseArea.doubleClicked`, which would change click behavior.
Diagnostics still add timing overhead; they are not timing-neutral acceptance.

## Interpreting a failed click

| Observation | Supported next discriminator |
| --- | --- |
| No window press while capture is running | Input did not reach this observed window/filter. Check attested window identity, foreground state and native delivery; do not call it QML interception. |
| Window press/release, no target delivery or action | Compare geometry, target state and existing grabber. An anonymous higher input candidate can explain a fixture obstruction, but geometric order alone is not actual dispatch proof. |
| Target press, no release/action | Inspect ungrab/cancellation, held motion, target hide/disable and popup changes. A drag or navigation can intentionally cancel a click. |
| Target press/release, no action | Narrow to control activation semantics, movement/cancellation and enabled state. Delivery does not imply acceptance. |
| Action emitted, no expected UI outcome | Investigate the action handler/model using bounded state assertions. The input trace intentionally does not record media or arbitrary model state. |

`settled` runs at the next event-loop checkpoint; it is not a synchronous
post-event snapshot. `event_id` identifies its originating event, while
`sample_position` and state describe the current checkpoint. Batched input may
advance state before that checkpoint. Geometric candidates do not implement all
Qt delivery, popup, pointer-handler or native-window rules.

## Reproduction and sensitivity

`tests/test_qt_input_trace.py` verifies:

- Window and actual target delivery, held grab, focus and action in a normal click.
- A deliberately overlaid transparent MouseArea swallowing one or three
  **separated** clicks: window delivery exists; registered target delivery and
  action do not. The geometric stack contains the blocker above the action.
  Removing the blocker restores the next click. This is an observer-sensitivity
  fixture, not a discovered production overlay.
- Held Select press interrupted by navigation, a popup, disable, or explicit
  ungrab; the first and two later separated clicks all activate correctly.
- Cap/deadline disconnect and continued activation after tracing stops.
- Destroyed dynamic controls retire their identity/action mapping; later controls
  cannot inherit a role through native-address reuse.
- Tracing does not reintroduce the shared rapid double-click suppression.
- Private sentinel object names/media titles do not appear in JSON.

No natural persistent separated-click failure was reproduced in these bounded
sequences. No further behavioral patch is justified yet. Next diagnostic: run
this observer in the owner's isolated combined candidate, reproduce a physical
missed click while recording the exact target and visible result separately,
and compare the three delivery/action stages. Do not restart or instrument the
ordinary installed session to obtain that evidence.
