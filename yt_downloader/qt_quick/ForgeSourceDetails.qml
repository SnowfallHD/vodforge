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
    // Facts the file never recorded stay in Library details, not this summary.
    readonly property var recordedRows: (selectedFacts.rows || []).filter(row => row.value !== "Not recorded")
    readonly property int unrecordedCount: (selectedFacts.rows || []).length - recordedRows.length
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
        model: details.selectedFacts.rows.length ? details.recordedRows : [
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
            Layout.minimumWidth: 0
            Layout.maximumWidth: details.width
            Layout.topMargin: modelData.label === "Save to" ? 8 : 0
            spacing: 10
            Text {
                text: modelData.label
                color: theme.muted
                font.pixelSize: 14
                wrapMode: Text.WordWrap
                Layout.preferredWidth: 135
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
            }
            Text {
                objectName: modelData.label === "Save to" ? "forgeSourceDestination" : ""
                text: modelData.value
                color: theme.text
                font.pixelSize: 14
                wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredWidth: 0
            }
        }
    }
    Text {
        objectName: "forgeUnrecordedNote"
        visible: details.unrecordedCount > 0
        text: details.unrecordedCount === 1 ? "1 detail was not recorded for this file." :
              details.unrecordedCount + " details were not recorded for this file."
        color: theme.muted
        font.pixelSize: 13
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
        Layout.topMargin: 4
    }
    Item { Layout.fillHeight: true }
}
