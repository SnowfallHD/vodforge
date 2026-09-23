import QtQuick

Item {
    id: control
    property string label: ""
    property string icon: ""
    property bool selected: false
    property bool emphasized: false
    property string size: "default"
    signal activated()
    implicitWidth: Math.max(2 * buttonMetrics[size].horizontalPadding + caption.implicitWidth
                            + (icon.length ? buttonMetrics[size].iconPixels + 8 : 0), 44)
    implicitHeight: buttonMetrics[size].height
    activeFocusOnTab: true

    Image {
        anchors.fill: parent
        source: "image://vodforge/button/" + Math.max(1, Math.round(control.width))
                + "/" + Math.max(1, Math.round(control.height)) + "/"
                + (mouse.pressed ? "pressed" : (mouse.containsMouse || control.selected ? "hover" : "normal"))
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
        cursorShape: Qt.PointingHandCursor
        onClicked: control.activated()
    }
    Keys.onReturnPressed: control.activated()
    Keys.onSpacePressed: control.activated()
}
