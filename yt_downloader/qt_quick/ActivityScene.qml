import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: scene
    property var appBridge
    function showLatest() {
        Qt.callLater(function() {
            if (!scene.visible || !logViewport.contentItem) return
            logText.cursorPosition = logText.length
            logViewport.contentItem.contentY = Math.max(0,
                logViewport.contentItem.contentHeight - logViewport.height)
        })
    }
    onVisibleChanged: { if (visible) showLatest() }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 12
        spacing: 8
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
        ScrollView {
            id: logViewport
            objectName: "activityLogViewport"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            TextArea {
                id: logText
                objectName: "activityLogText"
                readOnly: true
                selectByMouse: true
                text: scene.visible ? scene.appBridge.activityLog : ""
                onTextChanged: scene.showLatest()
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
