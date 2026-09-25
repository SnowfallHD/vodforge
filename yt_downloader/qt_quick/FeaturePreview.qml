import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: preview
    objectName: "featurePreview"
    property string previewKey: ""
    property bool technical: false
    property bool ignorePlaylists: false
    property string mode: "Everyday"
    property string cookieMode: "Browser"
    property string demoFormat: "Original audio"
    property string demoLocalProfile: localVideoProfiles.length ? localVideoProfiles[0] : "720p"
    property int activityStep: 0
    readonly property int preferredWidth: previewKey === "ui-activity" ? 280 :
                                          previewKey === "welcome-activity" ? 300 :
                                          previewKey === "activity-mode" ? 470 :
                                          previewKey === "playlists" ? 220 :
                                          previewKey === "youtube-access" || previewKey === "youtube-access-expanded" ? 340 : 430
    readonly property int preferredHeight: previewKey === "ui-activity" || previewKey === "welcome-activity" ? 180 :
                                           previewKey === "activity-mode" ? 180 :
                                           previewKey === "playlists" ? 65 :
                                           previewKey === "youtube-access" ? 110 :
                                           previewKey === "youtube-access-expanded" ? 230 :
                                           ["library", "local-video", "player"].indexOf(previewKey) >= 0 ? 210 : 190

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
        RowLayout {
            visible: ["ui-activity", "activity-mode", "welcome-activity"].indexOf(preview.previewKey) >= 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8
            ActivityModeSlider {
                visible: preview.previewKey !== "ui-activity"
                technical: preview.technical
                Layout.alignment: Qt.AlignTop
                onSelected: function(value) { preview.technical = value }
            }
            ActivityLines {
                objectName: "featurePreviewActivityLines"
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                technical: preview.technical
                activityText: preview.previewKey === "ui-activity" ?
                      "Getting video information\nDownloading media\nConverting media\nChecking the output\n[success] Download complete" :
                  preview.technical ?
                      ["Video 1 of 1: selected format 270+251",
                       "Video 1 of 1: Auto CBR target 6000 kbps video + 192 kbps audio.",
                       "Video 1 of 1: downloading",
                       "Video 1 of 1: FFmpeg command started (1/1) using CPU libx264"].slice(0, Math.max(1, preview.activityStep - 5)).join("\n") :
                      ["Video 1 of 1 — analyzing source formats",
                       "Video 1 of 1 — downloading",
                       "Video 1 of 1 — transcoding",
                       "Video 1 of 1 — validating output",
                       "[success] Download complete"].slice(0, Math.min(5, preview.activityStep + 1)).join("\n")
            }
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
        ColumnLayout {
            objectName: "featurePreviewLibraryFields"
            visible: preview.previewKey === "library"
            Layout.fillWidth: true
            spacing: 3
            Text { text: "CATEGORY"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                objectName: "featurePreviewCategory"
                label: "Travel  ▾"
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                onActivated: categoryPreview.open()
            }
            Text { text: "YOUR TAGS"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            TextField {
                objectName: "featurePreviewTags"
                text: "mountains, quiet, inspiration"
                color: theme.text; font.pixelSize: 15
                leftPadding: 16; rightPadding: 16
                Layout.fillWidth: true; Layout.preferredHeight: 38
                background: StoneField {}
            }
            Text { text: "NOTES"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            TextField {
                objectName: "featurePreviewNotes"
                text: "A short film about finding peace in the mountains."
                color: theme.text; font.pixelSize: 15
                leftPadding: 16; rightPadding: 16
                Layout.fillWidth: true; Layout.preferredHeight: 38
                background: StoneField {}
            }
        }
        ColumnLayout {
            objectName: "featurePreviewLocalVideoFields"
            visible: preview.previewKey === "local-video"
            Layout.fillWidth: true
            spacing: 3
            Text { text: "MP3 AUDIO"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            TextField {
                objectName: "featurePreviewLocalAudio"
                text: "Choose an MP3 file"; color: theme.text; font.pixelSize: 15
                leftPadding: 16; rightPadding: 16
                Layout.fillWidth: true; Layout.preferredHeight: 38
                background: StoneField {}
            }
            Text { text: "STILL IMAGE"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            TextField {
                objectName: "featurePreviewLocalImage"
                text: "Choose a still image"; color: theme.text; font.pixelSize: 15
                leftPadding: 16; rightPadding: 16
                Layout.fillWidth: true; Layout.preferredHeight: 38
                background: StoneField {}
            }
            Text { text: "OUTPUT PROFILE"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                objectName: "featurePreviewLocalProfile"
                label: preview.demoLocalProfile + "  ▾"
                Layout.fillWidth: true; Layout.preferredHeight: 38
                onActivated: localProfilePreview.open()
            }
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
        id: categoryPreview
        objectName: "featurePreviewCategoryMenu"
        x: Math.max(0, (preview.width - width) / 2)
        y: Math.max(0, (preview.height - height) / 2)
        width: Math.min(300, preview.width - 12)
        height: 45; padding: 3
        background: StoneField {}
        StoneButton {
            anchors.fill: parent
            label: "Travel"; selected: true
            onActivated: categoryPreview.close()
        }
    }
    Popup {
        id: localProfilePreview
        objectName: "featurePreviewLocalProfileMenu"
        x: Math.max(0, (preview.width - width) / 2)
        y: Math.max(0, (preview.height - height) / 2)
        width: Math.min(300, preview.width - 12)
        height: localVideoProfiles.length * 39 + 6; padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            Repeater {
                model: localVideoProfiles
                StoneButton {
                    required property string modelData
                    width: parent.width; height: 39
                    label: modelData
                    selected: preview.demoLocalProfile === modelData
                    onActivated: { preview.demoLocalProfile = modelData; localProfilePreview.close() }
                }
            }
        }
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
