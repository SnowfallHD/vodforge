import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Window {
    id: window
    visible: true
    width: 1100
    height: 740
    x: 30
    y: 30
    minimumWidth: 820
    minimumHeight: 560
    title: "VODForge — Qt Quick prototype"
    color: theme.bg

    Image {
        id: artwork
        objectName: "fullCoverArtwork"
        anchors.fill: parent
        source: "image://vodforge/backdrop"
        fillMode: Image.PreserveAspectCrop
        smooth: true
        cache: true
    }

    property int gutter: width < 960 ? 22 : 38
    property int rowGap: 14
    property string outputFormat: "MP4"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: window.gutter
        spacing: window.rowGap

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            spacing: 10
            Text {
                text: "VF  VODForge"
                color: theme.text
                font.family: "Arial"
                font.pixelSize: 22
                font.bold: true
                Layout.preferredWidth: window.width < 960 ? 158 : 198
            }
            Repeater {
                model: ["Forge", "Library", "Watch", "Activity"]
                StoneButton {
                    required property string modelData
                    label: modelData
                    selected: bridge.selection === modelData
                    icon: "image://vodforge/icon/" + (
                        modelData === "Forge" ? "download-20.png" :
                        modelData === "Library" ? "folder-20.png" :
                        modelData === "Watch" ? "play.png" : "activity-20.png")
                    Layout.preferredWidth: window.width < 960 ? 93 : 108
                    Layout.preferredHeight: 40
                    onActivated: bridge.select(modelData)
                }
            }
            Item { Layout.fillWidth: true }
            StoneField {
                Layout.preferredWidth: window.width < 960 ? 150 : 220
                Layout.preferredHeight: 40
                focused: searchInput.activeFocus
                TextField {
                    id: searchInput
                    anchors.fill: parent
                    anchors.leftMargin: 15
                    anchors.rightMargin: 12
                    placeholderText: "Search your library…"
                    color: theme.text
                    placeholderTextColor: theme.muted
                    background: Item {}
                    font.pixelSize: 15
                    onAccepted: bridge.select("Library")
                }
            }
            StoneButton {
                label: "⚙"
                Layout.preferredWidth: 46
                Layout.preferredHeight: 40
                onActivated: bridge.select("Forge")
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: theme.border
        }

        ColumnLayout {
            visible: bridge.selection === "Forge"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: window.rowGap

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 52
                spacing: 12
                StoneField {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    focused: urlInput.activeFocus
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 9
                        Text {
                            text: "🔗"
                            color: theme.action
                            font.pixelSize: 17
                            Layout.preferredWidth: 25
                        }
                        TextField {
                            id: urlInput
                            objectName: "forgeUrlInput"
                            Layout.fillWidth: true
                            placeholderText: "Paste a video URL"
                            color: theme.text
                            placeholderTextColor: theme.muted
                            background: Item {}
                            font.pixelSize: 16
                            onAccepted: bridge.submit(text, window.outputFormat)
                        }
                        Rectangle {
                            Layout.preferredWidth: 1
                            Layout.preferredHeight: 26
                            color: theme.border
                        }
                        StoneButton {
                            label: window.outputFormat + "  ▾"
                            Layout.preferredWidth: 92
                            Layout.preferredHeight: 38
                            onActivated: formatMenu.open()
                        }
                    }
                }
                StoneButton {
                    label: "Options"
                    Layout.preferredWidth: 100
                    Layout.preferredHeight: 44
                    onActivated: optionsMenu.open()
                }
                StoneButton {
                    label: "Download"
                    emphasized: true
                    Layout.preferredWidth: 134
                    Layout.preferredHeight: 44
                    onActivated: bridge.submit(urlInput.text, window.outputFormat)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                spacing: 10
                StoneButton {
                    label: "Load URL list"
                    Layout.preferredWidth: 128
                    Layout.preferredHeight: 42
                    onActivated: bridge.select("Forge")
                }
                Text {
                    text: "Save to"
                    color: theme.muted
                    font.pixelSize: 15
                    Layout.leftMargin: 10
                }
                StoneField {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    focused: pathInput.activeFocus
                    TextField {
                        id: pathInput
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 10
                        text: bridge.outputPath
                        color: theme.text
                        background: Item {}
                        font.pixelSize: 15
                        onAccepted: bridge.setOutputPath(text)
                    }
                }
                Text {
                    text: "Have local audio?"
                    color: theme.muted
                    font.pixelSize: 14
                }
                StoneButton {
                    label: "Create video"
                    Layout.preferredWidth: 132
                    Layout.preferredHeight: 42
                    onActivated: bridge.select("Forge")
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 128
                Layout.topMargin: 16
                spacing: 28
                Image {
                    source: assetUrl + "brand/icon-180.png"
                    Layout.preferredWidth: 68
                    Layout.preferredHeight: 68
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    spacing: 7
                    Text {
                        text: "Ready for a new run"
                        color: theme.text
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        text: "Paste a video URL above, then press Return to begin."
                        color: theme.muted
                        font.pixelSize: 15
                    }
                    Text {
                        text: "1080p Full HD  ·  Everyday"
                        color: theme.muted
                        font.pixelSize: 15
                    }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: "0%"
                    color: theme.selection
                    font.pixelSize: 34
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: theme.border
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 185
                spacing: 24
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 18
                    Text { text: bridge.status; color: theme.muted; font.pixelSize: 15 }
                    Text {
                        text: "◌   Your next run’s progress will appear here."
                        color: theme.muted
                        font.pixelSize: 17
                    }
                    Item { Layout.fillHeight: true }
                }
                ColumnLayout {
                    Layout.preferredWidth: Math.min(315, window.width * 0.28)
                    Layout.fillHeight: true
                    spacing: 11
                    Text {
                        text: "VOD-ready " + window.outputFormat + " / H.264 video / AAC audio"
                        color: theme.muted
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text { text: "Format             " + window.outputFormat; color: theme.muted; font.pixelSize: 14 }
                    Text { text: "Video               H.264"; color: theme.muted; font.pixelSize: 14 }
                    Text { text: "Audio               AAC"; color: theme.muted; font.pixelSize: 14 }
                    Text { text: "Output mode     Everyday"; color: theme.muted; font.pixelSize: 14 }
                    Item { Layout.fillHeight: true }
                }
            }

            Item { Layout.fillHeight: true }

            StoneField {
                Layout.fillWidth: true
                Layout.preferredHeight: 74
                Column {
                    anchors.fill: parent
                    anchors.margins: 17
                    spacing: 8
                    Text { text: "Your runs will collect here"; color: theme.text; font.pixelSize: 16; font.bold: true }
                    Text { text: "Start with a URL above. Completed downloads stay available in Library."; color: theme.muted; font.pixelSize: 14 }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 23
                Text { text: "No runs yet"; color: theme.muted; font.pixelSize: 14 }
                Item { Layout.fillWidth: true }
                Text { text: "Runs process one at a time"; color: theme.muted; font.pixelSize: 14 }
            }
        }

        Item {
            visible: bridge.selection !== "Forge"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Text {
                anchors.centerIn: parent
                text: bridge.selection + " is outside this Forge vertical slice."
                color: theme.muted
                font.pixelSize: 20
            }
        }
    }

    Popup {
        id: formatMenu
        x: Math.max(0, window.width - window.gutter - 375)
        y: window.gutter + 112
        width: 112
        height: 150
        padding: 3
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 8 }
        Column {
            anchors.fill: parent
            spacing: 3
            Repeater {
                model: ["MP4", "MP3", "M4A"]
                StoneButton {
                    required property string modelData
                    width: 106
                    height: 44
                    label: modelData
                    selected: window.outputFormat === modelData
                    onActivated: { window.outputFormat = modelData; formatMenu.close() }
                }
            }
        }
    }
    Popup {
        id: optionsMenu
        x: Math.max(0, window.width - window.gutter - 265)
        y: window.gutter + 112
        width: 190
        height: 95
        padding: 3
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 8 }
        Column {
            anchors.fill: parent
            spacing: 3
            StoneButton { width: 184; height: 42; label: "Everyday"; selected: true; onActivated: optionsMenu.close() }
            StoneButton { width: 184; height: 42; label: "Custom"; onActivated: optionsMenu.close() }
        }
    }
}
