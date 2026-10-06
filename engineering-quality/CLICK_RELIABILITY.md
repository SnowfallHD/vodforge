# Shared input reliability

The October 2026 investigation identified two independently reproducible defects.
Neither establishes the cause of the reported persistent physical-click failure.

## Rapid action clicks

`StoneButton` connected `MouseArea.doubleClicked` unconditionally and forwarded
it to `doubleActivated`. Only `LibraryFolders` used that second action. Qt 6.11
suppresses the second normal click when this signal is connected, so an ordinary
Select/Done button lost the second activation of a rapid pair.

Connect the double-click handler only when `doubleActivationEnabled` is true.
Folder rows opt in and retain their distinct action. Other controls receive both
ordinary clicks, each through the existing release-based activation path.

A handler that sets `event.accepted = false` is insufficient in Qt 6.11:
`QQuickMouseArea::mouseDoubleClickEvent` sets its double-click state from
`isDoubleClickConnected() || me.isAccepted()`. The conditional `Connections`
target deliberately removes the connection for ordinary buttons.

References:
- [Qt 6.11 MouseArea implementation](https://github.com/qt/qtdeclarative/blob/6.11/src/quick/items/qquickmousearea.cpp)
- [Qt 6.11 QTest mouse event sequence](https://github.com/qt/qtbase/blob/6.11/src/testlib/qtestmouse.h)

## Keyboard traversal

`activeFocusOnTab` alone does not guarantee button traversal when Qt's platform
style hint is `TabFocusTextControls`. A Library test starting at header search
looped on that field for forty Tab presses. Engine creation now chooses
`TabFocusAllControls` for this application process. No system preference or
focus artwork is changed. Actual Tab/Shift-Tab, Space/Return, and popup Escape
are exercised; directly calling `forceActiveFocus` on a button alone would miss
the traversal defect.

## Regression matrix

All automated rows below use disposable fixture data and offscreen Qt. They do
not certify physical input, the installed release, or Windows native behavior.

| Area | Maintained coverage | Outcome required |
| --- | --- | --- |
| Library Select/Done | `test_qt_click_reliability.py::test_rapid_second_click_activates_selection_toggle` | Five complete rapid pairs produce ten activations and finish outside selection mode |
| Forge Options, Library Filter, Watch hero, Activity Settings | `test_repeated_and_interrupted_popup_gestures` | Rapid open/close, first reopen, Escape, release outside, route interruption, first subsequent click |
| My Files media row | `test_folder_rows_keep_distinct_double_activation` | One single and one double action open exact fixture details |
| App navigation | `test_navigation_hit_faces_and_disabled_action` | Repeated left/center/right face clicks reach each tab; disabled action does not fire |
| Keyboard | `test_engine_enables_button_traversal_from_text_only_policy` | Tab reaches Filter/Select from search; Space/Return toggle; Shift-Tab returns to Filter and Return opens it |
| Existing popups | `test_qt_interaction_invariants.py` | Trigger/outside/Escape dismissal, stale hover, explicit close, anchor placement and nested settings |
| Focus retirement | `test_qt_hidden_scene_focus.py` | Hidden editor focus retires; visible shared editor focus survives |
| Scroll and hover ownership | `test_qt_scroll_lifecycle.py`, `test_qt_overflow_action_pointer.py` | Scroll/grab retirement and exact owner action selection |
| Library section layout | `test_qt_library_selection_bar_placement.py` | Selection affordances remain in the intended section |

## Why the old tests missed this

Existing click regressions used separated `QTest.mouseClick` calls. Qt's test
helper advances its synthetic clock after default-delay releases specifically
to prevent accidental double-click classification. Direct signal activation also
bypasses pointer classification. Existing keyboard cases explicitly focused a
button or checked only that the next focus item was visible. Those checks did
not require Tab to reach an action from a text-only platform policy.

Use the full QWindow `QTest.mouseDClick` sequence for rapid pairs. An isolated
manually sent double-click event does not include the platform press sequence
and must not be treated as equivalent proof. Instrumentation must not connect
to `MouseArea.doubleClicked` merely to count events, because that changes the
behavior being measured. Observe the window events or action signal instead.

## Remaining acceptance

The user's earlier three failed physical Done clicks remain unexplained. The
saved production capture had no input trace. Accessibility activation and later
bounded automated pointer successes prove only their own observed states. A
future isolated native candidate session should correlate delivered window
events, hit target/geometry, current grabber, popup visibility and action outcome
while exercising physical clicks, touchpad scrolling, native focus changes,
interrupted header drags, and rapid popup close/reopen. Do not inject a debugger,
change OS security settings, or reset the user's production library to obtain
that evidence.
