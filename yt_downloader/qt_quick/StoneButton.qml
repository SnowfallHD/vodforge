import QtQuick

Item {
    id: control
    property string label: ""
    property string icon: ""
    property bool selected: false
    property bool emphasized: false
    property bool transientMaterial: true
    property bool interactive: true
    property string size: "default"
    signal activated()
    implicitWidth: Math.max(2 * buttonMetrics[size].horizontalPadding + caption.implicitWidth
                            + (icon.length ? buttonMetrics[size].iconPixels + 8 : 0), 44)
    implicitHeight: buttonMetrics[size].height
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: control.label
    Accessible.focusable: control.interactive && control.enabled
    Accessible.focused: control.activeFocus
    Accessible.onPressAction: {
        if (control.interactive && control.enabled) control.activated()
    }

    Image {
        anchors.fill: parent
        source: "image://vodforge/button/" + Math.max(1, Math.round(control.width))
                + "/" + Math.max(1, Math.round(control.height)) + "/"
                + (!control.transientMaterial ? "normal" : mouse.pressed ? "pressed" : (mouse.containsMouse || control.selected ? "hover" : "normal"))
                + "/" + (control.emphasized ? "1" : "0")
        fillMode: Image.Stretch
        cache: true
        smooth: true
    }
    Row {
        anchors.centerIn: parent
        spacing: 8
        Image {
            visible: control.icon.length > 0
            width: visible ? buttonMetrics[control.size].iconPixels : 0
            height: buttonMetrics[control.size].iconPixels
            source: control.icon
            fillMode: Image.PreserveAspectFit
            smooth: true
        }
        Text {
            id: caption
            text: control.label
            color: control.emphasized ? "#80d5ef" : theme.text
            font.family: buttonFontFamily
            font.pixelSize: buttonMetrics[control.size].fontPixels
            font.weight: Font.Normal
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: control.interactive
        cursorShape: Qt.PointingHandCursor
        onClicked: control.activated()
    }
    Keys.onReturnPressed: { if (control.interactive && control.enabled) control.activated() }
    Keys.onSpacePressed: { if (control.interactive && control.enabled) control.activated() }
}
