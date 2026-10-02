import QtQuick

// For informational text outside clickable cards/buttons. Keep actionable links
// and elided captions on their existing components until their interaction is explicit.
TextEdit {
    id: information
    property bool selectionEnabled: true
    readOnly: true
    textFormat: TextEdit.PlainText
    selectByMouse: selectionEnabled
    selectByKeyboard: selectionEnabled
    activeFocusOnTab: selectionEnabled
    wrapMode: TextEdit.WordWrap
    color: theme.text
    selectionColor: theme.selection
    selectedTextColor: theme.text
    Accessible.role: Accessible.StaticText
    Accessible.name: text
    Accessible.focusable: selectionEnabled
    Accessible.focused: activeFocus
    HoverHandler {
        enabled: information.selectionEnabled
        cursorShape: Qt.IBeamCursor
    }
}
