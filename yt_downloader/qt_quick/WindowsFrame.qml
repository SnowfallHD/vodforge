import QtQuick
import QtQuick.Controls

// One application-owned frame for both Windows main and floating windows.
Item {
    id: frame
    required property var appWindow
    property color surfaceColor: theme.bg
    readonly property bool active: Qt.platform.os === "windows" && appWindow.visibility !== Window.FullScreen
    readonly property int headerHeight: active ? 32 : 0
    anchors.fill: parent
    visible: active
    z: 1000
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        height: frame.headerHeight
        color: frame.surfaceColor
        Text {
            anchors.left: parent.left
            anchors.leftMargin: 14
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 166
            text: frame.appWindow.title
            elide: Text.ElideRight
            color: theme.muted
            font.family: buttonFontFamily
            font.pixelSize: 12
        }
        MouseArea {
            anchors.fill: parent
            anchors.rightMargin: 138
            onPressed: frame.appWindow.startSystemMove()
            onDoubleClicked: frame.appWindow.visibility === Window.Maximized ? frame.appWindow.showNormal() : frame.appWindow.showMaximized()
        }
        Row {
            anchors.right: parent.right
            height: parent.height
            Repeater {
                model: ["Minimize", "Maximize", "Close"]
                delegate: StoneButton {
                    required property string modelData
                    objectName: "window" + modelData
                    width: 46
                    height: frame.headerHeight
                    size: "inline"
                    accessibilityLabel: modelData === "Maximize" && frame.appWindow.visibility === Window.Maximized ? "Restore" : modelData
                    label: modelData === "Minimize" ? "−" : modelData === "Maximize" ? (frame.appWindow.visibility === Window.Maximized ? "❐" : "□") : "×"
                    onActivated: {
                        if (modelData === "Minimize") frame.appWindow.showMinimized()
                        else if (modelData === "Maximize") frame.appWindow.visibility === Window.Maximized ? frame.appWindow.showNormal() : frame.appWindow.showMaximized()
                        else frame.appWindow.close()
                    }
                }
            }
        }
    }
}
