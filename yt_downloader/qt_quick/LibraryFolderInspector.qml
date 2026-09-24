import QtQuick
import QtQuick.Controls

Column {
    id: inspector
    objectName: "libraryFolderInspector"
    property var appBridge
    readonly property var item: appBridge.libraryFolderInspector
    property string section: "Item"
    spacing: 8

    Text {
        text: "SELECTED ITEM"
        color: theme.muted
        font.pixelSize: 12
        font.bold: true
    }
    Row {
        objectName: "libraryFolderOverview"
        width: parent.width
        height: 81
        spacing: 12
        StoneField {
            width: 124; height: 70
            Image {
                anchors.fill: parent
                anchors.margins: 3
                source: inspector.item.artwork || ""
                visible: source.toString().length > 0
                fillMode: Image.PreserveAspectCrop
                smooth: true
            }
        }
        Column {
            width: Math.max(130, inspector.width - 136)
            spacing: 4
            Text {
                objectName: "libraryFolderSelectedTitle"
                text: inspector.item.title || "Choose a saved item to inspect its metadata."
                color: theme.text
                font.pixelSize: 15
                font.bold: true
                width: parent.width
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Text {
                text: [inspector.item.creator, inspector.item.type].filter(Boolean).join("  ·  ")
                color: theme.muted
                font.pixelSize: 12
                width: parent.width
                elide: Text.ElideRight
            }
            Text {
                objectName: "libraryFolderSelectedLocation"
                text: inspector.item.location || ""
                color: theme.muted
                font.pixelSize: 12
                width: parent.width
                elide: Text.ElideRight
            }
        }
    }
    Row {
        spacing: 8
        StoneButton {
            objectName: "libraryFolderItemTab"
            label: "Item"
            selected: inspector.section === "Item"
            width: 84; height: 36
            onActivated: inspector.section = "Item"
        }
        StoneButton {
            objectName: "libraryFolderDescriptionTab"
            label: "Description"
            selected: inspector.section === "Description"
            width: 140; height: 36
            onActivated: inspector.section = "Description"
        }
    }
    StoneField {
        objectName: "libraryFolderDetailsPanel"
        width: parent.width
        height: 360
        Item {
            anchors.fill: parent
            anchors.margins: 10
            visible: inspector.section === "Item"
            Column {
                anchors.fill: parent
                spacing: 10
                Text { text: "Saved version"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Flow {
                    width: parent.width
                    spacing: 5
                    Repeater {
                        model: inspector.item.versions || []
                        StoneButton {
                            required property var modelData
                            label: modelData.label
                            selected: modelData.owner === inspector.item.owner
                            size: "inline"
                            width: Math.min(parent.width, implicitWidth)
                            onActivated: inspector.appBridge.chooseLibraryFolderInspectorVersion(modelData.owner)
                        }
                    }
                }
                Text { text: "Tags"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                ScrollView {
                    width: parent.width
                    height: 54
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    Text {
                        text: (inspector.item.tags || []).join(", ") || "No tags yet"
                        width: parent.width
                        color: theme.text
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                    }
                }
                Text { text: "Your note"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Text {
                    text: inspector.item.note || ""
                    color: theme.muted
                    font.pixelSize: 13
                    width: parent.width
                    wrapMode: Text.WordWrap
                    maximumLineCount: 3
                    elide: Text.ElideRight
                }
            }
        }
        Item {
            anchors.fill: parent
            anchors.margins: 10
            visible: inspector.section === "Description"
            Text {
                objectName: "libraryFolderDescriptionHeading"
                text: "DESCRIPTION"
                color: theme.muted
                font.pixelSize: 12
                font.bold: true
            }
            ScrollView {
                id: descriptionScroll
                objectName: "libraryFolderDescriptionScroll"
                x: 0; y: 25
                width: parent.width
                height: parent.height - y
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Text {
                    objectName: "libraryFolderDescriptionText"
                    text: inspector.item.descriptionInput || ""
                    width: descriptionScroll.availableWidth
                    color: theme.text
                    font.pixelSize: 14
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
    StoneButton {
        objectName: "libraryFolderOpenDetails"
        label: "Open details"
        width: parent.width; height: 40
        enabled: !!inspector.item.owner
        onActivated: inspector.appBridge.openSelectedLibraryFolderDetail()
    }
}
