import QtQuick
import QtQuick.Controls

// One application-owned frame for both Windows main and floating windows.
Item {
    id: frame
    required property var appWindow
    property color surfaceColor: theme.bg
    readonly property bool active: Qt.platform.os === "windows" && appWindow.visibility !== Window.FullScreen
    readonly property int headerHeight: active ? 32 : 0
    readonly property bool resizeEnabled: active && enabled && appWindow.visible &&
            appWindow.visibility === Window.Windowed
    readonly property int resizeMargin: 6
    // Corners own both axes; straight edges stop before the corner squares.
    // Keep these above the title bar so a top-edge press cannot become a move.
    readonly property var resizeZones: [
        {name: "topLeft", edges: Qt.TopEdge | Qt.LeftEdge, cursor: Qt.SizeFDiagCursor, column: 0, row: 0},
        {name: "top", edges: Qt.TopEdge, cursor: Qt.SizeVerCursor, column: 1, row: 0},
        {name: "topRight", edges: Qt.TopEdge | Qt.RightEdge, cursor: Qt.SizeBDiagCursor, column: 2, row: 0},
        {name: "left", edges: Qt.LeftEdge, cursor: Qt.SizeHorCursor, column: 0, row: 1},
        {name: "right", edges: Qt.RightEdge, cursor: Qt.SizeHorCursor, column: 2, row: 1},
        {name: "bottomLeft", edges: Qt.BottomEdge | Qt.LeftEdge, cursor: Qt.SizeBDiagCursor, column: 0, row: 2},
        {name: "bottom", edges: Qt.BottomEdge, cursor: Qt.SizeVerCursor, column: 1, row: 2},
        {name: "bottomRight", edges: Qt.BottomEdge | Qt.RightEdge, cursor: Qt.SizeFDiagCursor, column: 2, row: 2}
    ]
    anchors.fill: parent
    visible: active
    z: 1000
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        height: frame.headerHeight
        // The window already owns the artwork, including the native-frame strip.
        color: "transparent"
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
    Repeater {
        model: frame.resizeZones
        delegate: MouseArea {
            required property var modelData
            objectName: "windowResize" + modelData.name
            x: modelData.column === 0 ? 0 : modelData.column === 1 ? frame.resizeMargin : frame.width - frame.resizeMargin
            y: modelData.row === 0 ? 0 : modelData.row === 1 ? frame.resizeMargin : frame.height - frame.resizeMargin
            width: modelData.column === 1 ? Math.max(0, frame.width - 2 * frame.resizeMargin) : frame.resizeMargin
            height: modelData.row === 1 ? Math.max(0, frame.height - 2 * frame.resizeMargin) : frame.resizeMargin
            z: 1
            enabled: frame.resizeEnabled &&
                    (!(modelData.edges & (Qt.LeftEdge | Qt.RightEdge)) || frame.appWindow.maximumWidth > frame.appWindow.minimumWidth) &&
                    (!(modelData.edges & (Qt.TopEdge | Qt.BottomEdge)) || frame.appWindow.maximumHeight > frame.appWindow.minimumHeight)
            visible: enabled
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton
            cursorShape: modelData.cursor
            onPressed: (mouse) => {
                // Keep the press consumed: rejecting it forwards the same top-edge
                // press to the title-bar move handler beneath this resize zone.
                frame.appWindow.startSystemResize(modelData.edges)
            }
        }
    }

}
