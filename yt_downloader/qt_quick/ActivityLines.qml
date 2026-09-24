import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: activity
    objectName: "activityLines"
    property string activityText: ""
    property bool technical: false
    property var lines: []
    onActivityTextChanged: lines = activityText.split("\n")
    spacing: technical ? 3 : 8

    Repeater {
        model: activity.lines
        RowLayout {
            required property string modelData
            visible: modelData.length > 0
            Layout.fillWidth: true
            spacing: 10
            readonly property bool success: modelData.toLowerCase().indexOf("[success]") >= 0 ||
                                            modelData === "Completed"
            readonly property bool error: modelData.indexOf("ERROR:") === 0
            readonly property bool warning: modelData.indexOf("WARNING:") === 0
            Image {
                objectName: "activityLineEmblem"
                source: "image://vodforge/activity-icon/" +
                        (success ? "check" : error ? "error" : warning ? "warning" : "circle-dashed") +
                        "/r" + bridge.themeRevision
                Layout.preferredWidth: 16
                Layout.preferredHeight: 16
                Layout.alignment: Qt.AlignTop
                fillMode: Image.PreserveAspectFit
                smooth: true
            }
            Text {
                text: modelData.replace(/^\[(info|download|debug|success|warning|error)\]\s*/i, "")
                color: error ? theme.danger : warning ? theme.warning : theme.muted
                font.pixelSize: 14
                font.family: activity.technical ? monoFontFamily : buttonFontFamily
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }
}
