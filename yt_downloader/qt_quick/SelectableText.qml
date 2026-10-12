import QtQuick
import QtQuick.Controls

// For informational text outside clickable cards/buttons. Keep actionable links
// and elided captions on their existing components until their interaction is explicit.
TextArea {
    id: information
    property bool selectionEnabled: true
    // Preserve Qt's lazy standard menu. Native-popup qualification remains open;
    // the Basic style's standard Qt popup keeps its supported editing actions.
    function standardContextMenu() { return ContextMenu.menu }
    padding: 0
    background: null
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
