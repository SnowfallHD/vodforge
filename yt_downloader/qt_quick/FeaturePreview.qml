import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

StoneField {
    id: preview
    objectName: "featurePreview"
    property string previewKey: ""
    property bool technical: false
    property bool ignorePlaylists: false
    property string mode: "Everyday"
    property string cookieMode: "Browser"
    property string demoFormat: "Original audio"
    property int activityStep: 0
    interactive: false

    Timer {
        interval: preview.previewKey === "welcome-activity" ? 200 : 500
        repeat: true
        running: ["activity-mode", "welcome-activity"].indexOf(preview.previewKey) >= 0
        onTriggered: {
            preview.activityStep = (preview.activityStep + 1) % 15
            if (preview.activityStep === 0 || preview.activityStep === 12)
                preview.technical = false
            else if (preview.activityStep === 6)
                preview.technical = true
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 17
        spacing: 9
        Item { Layout.fillHeight: true; visible: preview.previewKey === "player" }
        Image {
            visible: preview.previewKey === "player"
            Layout.fillWidth: true
            Layout.preferredHeight: 118
            source: assetUrl + "preview_thumbnails/alpine-lake.jpg"
            fillMode: Image.PreserveAspectCrop
            smooth: true
        }
        Text {
            objectName: "featurePreviewActivityText"
            visible: ["ui-activity", "activity-mode", "welcome-activity"].indexOf(preview.previewKey) >= 0
            text: preview.previewKey === "ui-activity" ?
                      "Getting video information\nDownloading media\nConverting media\nChecking the output\nDownload complete" :
                  preview.technical ?
                      ["Video 1 of 1: selected format 270+251",
                       "Video 1 of 1: Auto CBR target 6000 kbps video + 192 kbps audio.",
                       "Video 1 of 1: downloading",
                       "Video 1 of 1: FFmpeg command started (1/1) using CPU libx264"].slice(0, Math.max(1, preview.activityStep - 5)).join("\n") :
                      ["Video 1 of 1 — analyzing source formats",
                       "Video 1 of 1 — downloading",
                       "Video 1 of 1 — transcoding",
                       "Video 1 of 1 — validating output",
                       "Completed"].slice(0, Math.min(5, preview.activityStep + 1)).join("\n")
            color: theme.text
            font.family: monoFontFamily
            font.pixelSize: 13
            Layout.fillWidth: true
            lineHeight: 1.35
        }
        StoneButton {
            visible: ["activity-mode", "welcome-activity"].indexOf(preview.previewKey) >= 0
            label: preview.technical ? "Technical details" : "Friendly progress"
            selected: preview.technical
            Layout.preferredWidth: 185
            onActivated: preview.technical = !preview.technical
        }
        Text {
            visible: ["output-settings", "ui-settings"].indexOf(preview.previewKey) >= 0
            text: "OPTIMIZE FOR"
            color: theme.muted; font.pixelSize: 12; font.bold: true
        }
        StoneButton {
            visible: ["output-settings", "ui-settings"].indexOf(preview.previewKey) >= 0
            label: preview.mode + "  ▾"
            Layout.fillWidth: true
            onActivated: modePreview.open()
        }
        Text {
            visible: preview.previewKey === "output-settings"
            text: bridge.describeExportMode(preview.mode)
            color: theme.muted; font.pixelSize: 13
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }
        Text {
            visible: preview.previewKey === "ui-settings"
            text: "MP4 VIDEO  ·  1080p Full HD"
            color: theme.muted; font.pixelSize: 13
        }
        StoneButton {
            visible: preview.previewKey === "ui-settings"
            label: "Save thumbnail"
            selected: true
            Layout.preferredWidth: 170
        }
        Text {
            visible: preview.previewKey === "playlists"
            text: "BATCH AND PLAYLISTS"
            color: theme.muted; font.pixelSize: 12; font.bold: true
        }
        StoneButton {
            visible: preview.previewKey === "playlists"
            label: "Ignore playlists"
            selected: preview.ignorePlaylists
            Layout.preferredWidth: 190
            onActivated: preview.ignorePlaylists = !preview.ignorePlaylists
        }
        Text {
            visible: ["youtube-access", "youtube-access-expanded"].indexOf(preview.previewKey) >= 0
            text: "YOUTUBE ACCESS"
            color: theme.muted; font.pixelSize: 12; font.bold: true
        }
        RowLayout {
            visible: ["youtube-access", "youtube-access-expanded"].indexOf(preview.previewKey) >= 0
            Repeater {
                model: ["Public", "Browser", "cookies.txt"]
                StoneButton {
                    required property string modelData
                    label: modelData
                    selected: modelData === preview.cookieMode
                    Layout.preferredWidth: modelData === "cookies.txt" ? 124 : 95
                    onActivated: preview.cookieMode = modelData
                }
            }
        }
        StoneButton {
            visible: ["youtube-access", "youtube-access-expanded"].indexOf(preview.previewKey) >= 0
            label: "Chrome  ▾"
            Layout.preferredWidth: 170
            onActivated: browserPreview.open()
        }
        Text {
            visible: preview.previewKey === "library"
            text: "CATEGORY  ·  Travel\nYOUR TAGS  ·  mountains, quiet, inspiration\nNOTES  ·  A short film about finding peace in the mountains."
            color: theme.text; font.pixelSize: 13
            Layout.fillWidth: true; wrapMode: Text.WordWrap; lineHeight: 1.5
        }
        Text {
            visible: preview.previewKey === "local-video"
            text: "MP3 AUDIO  ·  Choose an MP3 file\nSTILL IMAGE  ·  Choose a still image\nOUTPUT PROFILE  ·  720p"
            color: theme.text; font.pixelSize: 13
            Layout.fillWidth: true; wrapMode: Text.WordWrap; lineHeight: 1.5
        }
        RowLayout {
            visible: ["ui-player", "player"].indexOf(preview.previewKey) >= 0
            Layout.fillWidth: true
            StoneButton { label: "▶"; accessibilityLabel: "Play preview"; Layout.preferredWidth: 46 }
            Text { text: "0:00 / 32:47"; color: theme.muted; font.pixelSize: 13 }
            Item { Layout.fillWidth: true }
            Text { text: "Volume"; color: theme.muted; font.pixelSize: 13 }
            StoneField { Layout.preferredWidth: 90; Layout.preferredHeight: 12; interactive: false }
        }
        Text {
            visible: preview.previewKey === "player"
            text: "PREVIEW MOMENTS"
            color: theme.muted; font.pixelSize: 12
        }
        Text {
            visible: preview.previewKey === "ui-player"
            text: "Player controls  ·  Play  ·  Seek  ·  Volume"
            color: theme.text; font.pixelSize: 14
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }
        ColumnLayout {
            visible: preview.previewKey === "original-audio"
            Layout.fillWidth: true
            spacing: 4
            StoneButton {
                objectName: "featurePreviewFormatField"
                label: preview.demoFormat + "  ▾"
                accessibilityLabel: "Example output format"
                Layout.fillWidth: true
                onActivated: preview.demoFormat = "Original audio"
            }
            Repeater {
                model: ["MP4", "MP3", "Original audio"]
                StoneButton {
                    required property string modelData
                    objectName: "featurePreviewFormatOption_" + modelData.replace(" ", "_")
                    label: modelData
                    selected: preview.demoFormat === modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 39
                    onActivated: preview.demoFormat = modelData
                }
            }
        }
        Item { Layout.fillHeight: true }
    }
    Popup {
        id: modePreview
        x: Math.max(0, (preview.width - width) / 2)
        y: Math.max(0, (preview.height - height) / 2)
        width: Math.min(300, preview.width - 12)
        height: 6 * 39 + 6
        padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 0
            Repeater {
                model: bridge.exportModeOptions
                StoneButton {
                    required property var modelData
                    width: parent.width
                    height: 39
                    label: modelData.label
                    selected: preview.mode === modelData.label
                    onActivated: { preview.mode = modelData.label; modePreview.close() }
                }
            }
        }
    }
    Popup {
        id: browserPreview
        x: Math.max(0, (preview.width - width) / 2)
        y: Math.max(0, (preview.height - height) / 2)
        width: 220; height: 136; padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent; spacing: 2
            Repeater {
                model: ["Chrome", "Edge", "Firefox"]
                StoneButton {
                    required property string modelData
                    width: parent.width; height: 42; label: modelData
                    onActivated: browserPreview.close()
                }
            }
        }
    }
}
