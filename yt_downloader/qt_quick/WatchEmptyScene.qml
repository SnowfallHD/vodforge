import QtQuick

Column {
    id: empty
    objectName: "watchEmptyScene"
    property var appBridge
    width: parent.width
    spacing: 0

    Item {
        width: parent.width
        height: 415
        StoneField { anchors.left: parent.left; anchors.right: parent.right; height: 394 }
        Text {
            x: 36; y: 31
            text: "W E L C O M E   T O   V O D F O R G E"
            color: theme.muted
            font.pixelSize: 11
        }
        Text {
            objectName: "watchEmptyTitle"
            x: 36; y: 58
            text: "Nothing to watch yet"
            color: theme.text
            font.pixelSize: 40
            font.bold: true
        }
        Text {
            x: 36; y: 116
            width: Math.min(560, parent.width - 72)
            text: "Your downloaded videos and audio will appear here\nand be turned into a beautiful, streaming-like\nviewing experience automatically."
            color: theme.muted
            font.pixelSize: 21
            lineHeight: 1.15
        }
        StoneButton {
            objectName: "watchEmptyGoForge"
            x: 36; y: 219; width: 217; height: 44
            label: "Go to Forge"
            emphasized: true
            onActivated: empty.appBridge.select("Forge")
        }
        StoneButton {
            objectName: "watchEmptyOpenLibrary"
            x: 270; y: 219; width: 225; height: 44
            label: "Open Library"
            onActivated: empty.appBridge.select("Library")
        }
        Rectangle { x: 36; y: 306; width: 459; height: 1; color: theme.border }
        Text {
            x: 48; y: 328; text: "ⓘ"
            color: theme.muted; font.pixelSize: 22
        }
        Text {
            x: 82; y: 328
            width: Math.min(475, parent.width - 118)
            text: "Download a video in Forge or import media in Library\nto get started. It will show up here automatically."
            color: theme.muted
            font.pixelSize: 16
        }
        Image {
            visible: parent.width >= 1000
            x: parent.width * .73 - 128; y: 42
            width: 256; height: 218
            source: "image://vodforge/watch-welcome/r" + empty.appBridge.themeRevision
            fillMode: Image.PreserveAspectFit
        }
        Text {
            visible: parent.width >= 1000
            x: parent.width * .73 - 174; y: 272
            text: "Download. Organize. Watch Anywhere."
            color: theme.muted; font.pixelSize: 18
        }
        Text {
            visible: parent.width >= 1000
            x: parent.width * .73 - 112; y: 307
            text: "Y O U R   M E D I A .   Y O U R   W A Y."
            color: theme.muted; font.pixelSize: 11
        }
    }

    Repeater {
        model: [
            { title: "Recently Added", cardHeight: 132 },
            { title: "Playlists", cardHeight: 100 },
            { title: "Channels", cardHeight: 96 }
        ]
        Column {
            id: section
            required property var modelData
            width: empty.width
            spacing: 0
            Text {
                height: 41
                text: section.modelData.title
                color: theme.text
                font.pixelSize: 23
                font.bold: true
            }
            Row {
                width: parent.width
                spacing: 14
                readonly property int columns: Math.max(1, Math.min(4, Math.floor((width + spacing) / 280)))
                readonly property real tileWidth: (width - spacing * (columns - 1)) / columns
                Repeater {
                    model: parent.columns
                    Item {
                        width: parent.tileWidth
                        height: section.modelData.cardHeight
                        StoneField { anchors.fill: parent }
                        SceneIcon {
                            name: section.modelData.title === "Channels" ? "channels" : section.modelData.title === "Playlists" ? "list" : "videos"
                            tone: theme.border
                            x: section.modelData.title === "Recently Added" ? (parent.width - 44) / 2 : 30
                            y: section.modelData.title === "Recently Added" ? 35 : 28
                            width: 44; height: 44
                        }
                        Rectangle {
                            x: section.modelData.title === "Recently Added" ? 26 : 110
                            y: section.modelData.title === "Recently Added" ? 92 : 39
                            width: Math.max(20, parent.width - (section.modelData.title === "Recently Added" ? 96 : 196))
                            height: 10; radius: 5; color: theme.border
                        }
                        Rectangle {
                            x: section.modelData.title === "Recently Added" ? 26 : 110
                            y: section.modelData.title === "Recently Added" ? 111 : 61
                            width: Math.max(20, parent.width / 2 - 54)
                            height: 10; radius: 5; color: theme.border
                        }
                    }
                }
            }
            Item { width: 1; height: 27 }
        }
    }
}
