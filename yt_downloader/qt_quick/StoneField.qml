import QtQuick
import QtQuick.Window

Item {
    id: field
    property bool focused: false
    property real surfaceOpacity: Window.window && Window.window.glassControlOpacity !== undefined
                                  ? Window.window.glassControlOpacity : 1.0
    property bool interactive: false
    property string accessibilityLabel: ""
    signal activated()
    implicitHeight: 48
    activeFocusOnTab: interactive
    Accessible.role: interactive ? Accessible.Button : Accessible.NoRole
    Accessible.name: accessibilityLabel
    Accessible.focusable: interactive
    Accessible.focused: activeFocus
    Accessible.onPressAction: { if (interactive && enabled) activated() }
    Image {
        opacity: field.surfaceOpacity
        property string presentationRole: "control"
        anchors.fill: parent
        // Hidden scenes retain their fields; admit material work only when visible.
        source: visible ? ("image://vodforge/field/" + Math.max(1, Math.round(field.width))
                + "/" + Math.max(1, Math.round(field.height))
                + "/" + (field.focused ? "focus" : "normal") + "/r" + bridge.themeRevision) : ""
        fillMode: Image.Stretch
        cache: true
        smooth: true
    }
    MouseArea {
        anchors.fill: parent
        enabled: field.interactive
        cursorShape: Qt.PointingHandCursor
        onClicked: field.activated()
    }
    Keys.onReturnPressed: { if (interactive && enabled) activated() }
    Keys.onSpacePressed: { if (interactive && enabled) activated() }
}
