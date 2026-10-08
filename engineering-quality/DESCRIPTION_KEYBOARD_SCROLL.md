# Read-only description keyboard scrolling

Native private candidate 07a7a4d established description text focus by Tab after
Copy description, but arrows and PageDown did not move its viewport. The same
initial nine offscreen cases fail identically with the fdec43f wheel handler and
07a7a4d: five failures, four passes. LibraryDetail.qml and SelectableText.qml are
byte-identical between those commits. This is a pre-existing keyboard focus and
navigation gap in this bounded comparison, not a demonstrated regression from
the pointer-owned wheel fallback. It does not establish an earlier human baseline.

The fix is scoped to the Library description ScrollView and its read-only text.
Unmodified Up/Down scroll 32 points; PageUp/PageDown and Space scroll 90% of the
viewport; Shift-Space scrolls backward. An overflowing description contains those
keys at its limits. A description without overflow routes them to the nearest
overflowing ancestor. Text and parent focus use the same handler, before default
TextEdit handling can consume the keys. The wheel handler is unchanged.

Shift-arrows, modified navigation, Select All and Copy retain TextEdit handling.
Scrolling does not change cursor or selected text. The editable description is a
separate TextArea and has no added key handler; other SelectableText instances are
unchanged. No timer, focus forcing or application-wide key filter is introduced.

`tests/test_qt_description_keyboard.py` covers text versus ScrollView focus,
arrows, page keys, Space/Shift-Space, top/bottom containment, short-description page
scrolling and Shift-selection/Copy/Select All with selection preserved during
PageDown. Existing pointer, selection, lifecycle, geometry and hidden-focus tests
remain part of the focused verification.

Remaining native delta: rebuild/freeze the successor privately, coordinate GUI
before launch, Tab from Copy description into the long field and verify both
directions of arrows/page/Space, top/bottom containment and Shift-selection/Copy.
Verify short/empty keyboard page routing and one long/short/outside wheel spot
check. Do not claim native success from offscreen tests. Actual human trackpad
swipe/momentum/reversal remains pending; CUA wheel input does not prove it.
The already frozen 07a7a4d bundle is retained untouched. No source publication or
public release is part of this change.
