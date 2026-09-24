import QtQuick

Item {
    id: field
    property bool focused: false
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
        property string presentationRole: "control"
        anchors.fill: parent
        source: "image://vodforge/field/" + Math.max(1, Math.round(field.width))
                + "/" + Math.max(1, Math.round(field.height))
                + "/" + (field.focused ? "focus" : "normal") + "/r" + bridge.themeRevision
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
