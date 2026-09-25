import QtQuick
import QtQuick.Controls

Column {
    id: inspector
    objectName: "libraryFolderInspector"
    property var appBridge
    readonly property var item: appBridge.libraryFolderInspector
    property string section: "Item"
    property real targetPanelBottom: height
    spacing: 8

    Text {
        id: eyebrow
        text: "SELECTED ITEM"
        color: theme.muted
        font.pixelSize: 12
        font.bold: true
    }
    Row {
        id: overview
        objectName: "libraryFolderOverview"
        width: parent.width
        height: 81
        spacing: 12
        StoneField {
            width: 124; height: 70
            ArtworkImage {
                anchors.fill: parent
                source: inspector.item.artwork || ""
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
    StoneButton {
        id: openDetails
        objectName: "libraryFolderOpenDetails"
        label: "Open details"
        width: parent.width; height: 40
        enabled: !!inspector.item.owner
        onActivated: inspector.appBridge.openSelectedLibraryFolderDetail()
    }
    Item {
        width: 1
        height: Math.max(0, inspector.targetPanelBottom -
            (eyebrow.height + overview.height + openDetails.height + tabs.height + detailsPanel.height + inspector.spacing * 5))
    }
    Row {
        id: tabs
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
            onActivated: {
                inspector.section = "Description"
                Qt.callLater(function() { inspector.appBridge.attestQtLibraryVisibility() })
            }
        }
    }
    StoneField {
        id: detailsPanel
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
            anchors.bottomMargin: 0
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
}
