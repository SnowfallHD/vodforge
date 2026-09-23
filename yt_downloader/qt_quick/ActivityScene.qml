import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: scene
    property var appBridge

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 24
        spacing: 18
        RowLayout {
            Layout.fillWidth: true
            width: parent.width
            ColumnLayout {
                spacing: 8
                Text { text: "Activity"; color: theme.text; font.pixelSize: 40; font.bold: true }
                Text { text: scene.appBridge.status; color: theme.muted; font.pixelSize: 17; font.bold: true }
            }
            Item { Layout.fillWidth: true }
            StoneButton {
                label: "Open log folder"
                Layout.preferredWidth: 160
                Layout.preferredHeight: 40
                onActivated: scene.appBridge.openActivityLogFolder()
            }
        }
        Item { Layout.preferredHeight: 35 }
        ScrollView {
            id: logViewport
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            TextArea {
                id: logText
                readOnly: true
                selectByMouse: true
                text: scene.appBridge.activityLog
                color: theme.muted
                font.pixelSize: 14
                font.family: monoFontFamily
                wrapMode: TextArea.Wrap
                background: Item {}
                leftPadding: 0
                rightPadding: 10
                topPadding: 0
                bottomPadding: 15
            }
        }
    }
}
