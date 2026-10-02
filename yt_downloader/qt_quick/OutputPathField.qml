import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

StoneField {
    id: field
    property string path: ""
    implicitHeight: 34
    HoverHandler { id: pathHover }
    ToolTip {
        objectName: "outputPathTooltip"
        parent: field
        x: (field.width - width) / 2
        y: field.height + 6
        margins: 16
        padding: 10
        background: Rectangle {
            color: theme.surface_2
            radius: 8
            border.color: theme.border
        }
        visible: pathHover.hovered && !!field.path
        text: field.path
        width: Math.min(420, Math.max(80, field.Window.window ? field.Window.window.width - 32 : 420))
        contentItem: Text {
            text: field.path
            color: theme.text
            font.pixelSize: 13
            wrapMode: Text.WrapAnywhere
        }
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 8
        Image {
            source: "image://vodforge/icon/folder.png/r" + bridge.themeRevision
            Layout.preferredWidth: 18
            Layout.preferredHeight: 18
            fillMode: Image.PreserveAspectFit
        }
        Text {
            objectName: "outputPathText"
            text: field.path
            color: theme.text
            font.pixelSize: 15
            elide: Text.ElideLeft
            maximumLineCount: 1
            Layout.fillWidth: true
        }
    }
}
