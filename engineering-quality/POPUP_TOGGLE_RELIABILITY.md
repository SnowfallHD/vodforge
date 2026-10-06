# Popup close/reopen reliability — 2026-10-06

Scope: isolated source candidate based on `6cdea0e0b1ad324165aa148bc04f5726bef716dd`.
No installed app, production data, OS settings, native input injection or package
was changed. Qt fixture results are not proof of physical input behavior.

## Invariant and fixes

A single trigger gesture has one semantic result, even when Qt dismisses a popup
on press before the trigger activates on release. Hover motion inside that same
held gesture must not erase its dismissal identity. `StonePopup` now retains the
existing dismissal flag while any pointer button remains pressed; the existing
release checkpoint clears it. No debounce window or new timer is introduced.

A focus-opened suggestion list must distinguish a new editor focus request from
focus restored by closing that list. The annotation category editor previously
reopened on `Qt.PopupFocusReason`: observed visibility was `true, false, true`
for one close click. It now ignores that restoration reason. The arrow is also
registered as the popup trigger before the field can open the list; otherwise
its first click cannot be recognized as the current trigger's dismissal.

Mouse-focus opening leaves editing focus in the category field. Consequently,
Escape previously reached the enclosing annotation dialog and closed both
surfaces. The field consumes Escape only while its suggestions are visible;
otherwise it delegates Escape normally. Choice selection, arrow close/reopen,
first Escape and subsequent dialog Escape are checked separately.

## Source audit

- `StoneButton` owns release-based mouse activation and Space/Return. Ordinary
  controls no longer connect `MouseArea.doubleClicked` (earlier integrated fix).
- `Bridge.eventFilter` observes QWindow press coordinates and release; it returns
  false. The shared popup dismissal check uses the actual same-window press,
  not stale hover. Release notification is deferred until click handlers finish.
- `StonePopup` owns trigger identity and dismissal state. Its shadow is an Image
  outside the face; it adds no MouseArea or input handler.
- `AnchoredPopup` repositions/closes for hidden or off-viewport anchors. Its
  100 ms timer handles placement, not click debounce. Scroll and anchor lifecycle
  coverage remains in the existing interaction/overflow tests.
- Library Collections submenu sets trigger identity on hover before opening;
  repeated hover-open/click-close/click-open/click-close passed without a change.
- Category suggestions were the only focus-change auto-open path in this popup
  inventory. Settings closes its nested menus; annotation/local-conversion
  parents close their associated children. Existing focus-retirement tests cover
  hidden scenes.
- Basic Qt popup styling in the inspected PySide6 6.11.2 installation has no
  default enter/exit transition. An injected 140 ms exit transition also passes:
  a release during closing does not poison the next close. No animation fix is
  justified by that bounded check.

## Regression and inventory matrix

`tests/test_qt_popup_toggle_order.py` adds real QWindow event delivery in disposable
HOME/LOCALAPPDATA fixtures. Model setup can call bridge methods; trigger actions
under test use mouse or keyboard events, not emitted activation signals.

| Surfaces | Maintained proof and limits |
| --- | --- |
| Annotation category suggestions | Field-focus open; arrow, Escape and choice dismiss; close stays closed; arrow reopens; subsequent Escape closes dialog. Tracks visibility, focus reason and bounded input trace on failure. |
| Library Collections hover submenu | Hover opens; first click closes; subsequent clicks reopen/close. |
| Shared modeless dismissal | Forge Options and Settings fixtures set modeless: press trigger closes; leave and return while held; release stays closed; next click opens. This intentionally isolates shared behavior and is not native modal-overlay proof. |
| Settings quality, output mode, subtitles, theme, Help | Three rapid pairs and three separated pairs per surface; Space/Return open and Escape close; close/reopen settings and reuse. Scroll positions are set for reachable controls. |
| Forge format, MP3 options, local conversion, local profile, compact output details | Same repeated pointer/keyboard matrix; route interruption for format, MP3 and conversion. No conversion/download starts. |
| Support reason | Same repeated pointer/keyboard matrix using an isolated form; no submission. |
| Library sort, group menu, selection actions, saved-item actions | Same repeated pointer/keyboard matrix; sort also changes routes and returns. Fixture selection/details setup admits real owners. |
| Forge Options, Library Filter, Watch hero, Activity Settings | Earlier `test_qt_click_reliability::test_repeated_and_interrupted_popup_gestures`: rapid pairs, separated first reopen, Escape, cancelled press, route interruption. |
| Forge completed/active run actions, folder ancestors | Existing `test_qt_interaction_invariants::test_popup_trigger_click_closes_without_reopening`: repeated separated toggles, Escape, outside dismissal and reopen. |
| All Runs hover list | Source audit: hover opens, trigger click navigates, Escape closes. It is not a second-click toggle. Existing Run Deck/scroll coverage applies; no new rapid-pair toggle claim. |
| Compact selected issue/details; support diagnostics | Centered detail dialogs using shared StonePopup, source-audited; not individually exercised by this new pointer matrix. |
| YouTube access and update | Settings closes before these dialogs open, hiding the originating trigger. Source-audited transition dialogs; no repeated same-trigger contract or external operation tested here. |
| Native file/folder pickers and other confirmation/edit dialogs | Not dropdown toggles; source audit only in this round. Native picker/cross-platform behavior remains separate acceptance. |
| Keyboard traversal and hidden focus | Earlier click reliability test starts with text-only style policy and actually Tabs from search to Filter/Select; Space/Return/Shift-Tab verified. `test_qt_hidden_scene_focus.py` covers retirement. |
| Shared animated exit | 140 ms test transition; release during exit, reopen and close next cycle. Representative interleaving only. |

## Why earlier coverage missed these defects

The category regression directly emitted the arrow's activation signal. It never
focused the editor with a pointer, so it missed both automatic opening before
trigger registration and restored-focus reopening. Ordinary shared-popup tests
kept the pointer still during trigger dismissal or released outside; they did
not leave and return while the same press remained held. Earlier Escape checks
opened menus through a button, so the popup owned keyboard focus; they did not
exercise the category editor's retained-focus path.

The negative-control run restores just the two runtime QML files to the exact
base while retaining the new tests, then restores candidate bytes in `finally`.
Compare the baseline and candidate logs in the task's evidence folder. This is
prior-failure evidence, not a deliberate production mutation.

## Recorded source validation

With PySide6 6.11.2 and software/offscreen Qt, the final 22 new tests on the
unchanged base produced **5 failed, 17 passed**. The corrected candidate passed
**91 tests** across popup toggle order, click reliability, interaction invariants,
hidden-scene focus, scroll lifecycle, overflow action pointers and input tracing.
The new test file passes Ruff checking/formatting; the patch passes whitespace
checks. No native packaged acceptance is implied.

## Remaining acceptance

No observation here explains the user's three separated physical Done clicks
that did nothing in installed 0.2.4. The previously captured installed state lacks
input instrumentation. The bounded opt-in observer described in `INPUT_TRACE.md`
can distinguish window delivery, target delivery and action on an isolated native
candidate. Native physical verification and Windows/package parity remain open;
synthetic success, even spontaneous Qt events, does not close those gates.
