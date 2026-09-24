import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: details
    objectName: "forgeSourceDetails"
    property var appBridge
    property string outputFormat: "MP4"
    property string displayType: "MP4"
    property bool preview: false
    property bool showHeading: true
    property var selectedFacts: ({ heading: "", rows: [] })
    spacing: 8

    Text {
        visible: details.showHeading
        text: details.selectedFacts.heading || (details.preview ? "Preview: " + details.displayType + " · metadata only" :
              "Output: " + details.displayType + " · " + details.appBridge.exportModeLabel
        )
        color: theme.muted
        font.pixelSize: 14
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Repeater {
        model: details.selectedFacts.rows.length ? details.selectedFacts.rows : [
            { label: "Format", value: details.displayType },
            { label: "Video", value: details.preview ? "Not downloaded" : details.outputFormat === "MP4" ? "H.264" : "None" },
            { label: "Audio", value: details.preview ? "Not downloaded" : details.outputFormat === "MP3" ? "MP3" :
                                     details.outputFormat === "Original audio" ? "Source" :
                                     details.appBridge.exportMode === "Manual Override" ? details.appBridge.manualValues.manual_audio_codec : "AAC" },
            { label: "Output mode", value: details.preview ? "Preview only" : details.appBridge.exportModeLabel },
            { label: "Save to", value: details.appBridge.outputPath }
        ]
        RowLayout {
            required property var modelData
            Layout.fillWidth: true
            Layout.topMargin: modelData.label === "Save to" ? 8 : 0
            spacing: 10
            Text {
                text: modelData.label
                color: theme.muted
                font.pixelSize: 14
                wrapMode: Text.WordWrap
                Layout.preferredWidth: 135
                Layout.alignment: Qt.AlignTop
            }
            Text {
                objectName: modelData.label === "Save to" ? "forgeSourceDestination" : ""
                text: modelData.value
                color: theme.text
                font.pixelSize: 14
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
        }
    }
    Item { Layout.fillHeight: true }
}
