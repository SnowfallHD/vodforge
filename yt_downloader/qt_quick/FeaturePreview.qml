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
    interactive: false

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
            visible: ["ui-activity", "activity-mode", "welcome-activity"].indexOf(preview.previewKey) >= 0
            text: preview.technical ? "[download] Downloading media\n[info] Checking output\n[success] Download complete" :
                                      "Getting video information\nDownloading media\nConverting media\nChecking the output\nDownload complete"
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
            onActivated: preview.mode = preview.mode === "Everyday" ? "Editing" : "Everyday"
        }
        Text {
            visible: preview.previewKey === "output-settings"
            text: preview.mode === "Everyday" ? "Balanced quality and speed for everyday downloads." :
                                                     "Higher quality for editing and further processing."
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
            visible: ["transport", "original-audio"].indexOf(preview.previewKey) >= 0
            text: preview.previewKey === "original-audio" ? "ORIGINAL AUDIO\nSave the original audio stream when available." :
                                                               "Player controls  ·  Play  ·  Seek  ·  Volume"
            color: theme.text; font.pixelSize: 14
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }
        Item { Layout.fillHeight: true }
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
