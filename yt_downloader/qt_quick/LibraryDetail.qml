import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: detail
    property var appBridge
    signal actionsRequested(string owner)
    signal annotationRequested(string owner)
    readonly property var item: appBridge.libraryDetail
    readonly property bool compact: width < 1020

    ScrollView {
        id: viewport
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        Column {
            width: viewport.availableWidth
            spacing: 16
            StoneButton {
                label: detail.item.fromFolders ? "Back to folders" : "Back to Library"
                width: 180
                height: 40
                onActivated: detail.appBridge.returnLibraryDetails()
            }
            Flow {
                id: hero
                width: parent.width
                height: childrenRect.height
                spacing: 27
                StoneField {
                    width: detail.compact ? hero.width : Math.min(475, hero.width * 0.43)
                    height: detail.compact ? Math.min(360, width * 9 / 16) : 246
                    interactive: true
                    accessibilityLabel: "Play " + (detail.item.title || "saved media")
                    onActivated: detail.appBridge.openLibraryOwner(detail.item.owner)
                    ArtworkImage {
                        anchors.fill: parent
                        source: detail.item.artwork || ""
                    }
                    StoneButton {
                        anchors.centerIn: parent
                        width: 64
                        height: 64
                        label: "▶"
                        accessibilityLabel: "Play " + (detail.item.title || "saved media")
                        onActivated: detail.appBridge.openLibraryOwner(detail.item.owner)
                    }
                }
                Column {
                    width: detail.compact ? hero.width : hero.width - Math.min(475, hero.width * 0.43) - 27
                    spacing: 12
                    Text {
                        text: detail.item.title || "Saved media"
                        width: parent.width
                        color: theme.text
                        font.pixelSize: 32
                        font.bold: true
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                    Text {
                        text: [detail.item.category, detail.item.type, detail.item.creator].filter(Boolean).join("  ·  ")
                        width: parent.width
                        color: theme.muted
                        font.pixelSize: 15
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        text: detail.item.description || "Saved in your Library."
                        width: parent.width
                        color: theme.muted
                        font.pixelSize: 17
                        wrapMode: Text.WordWrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                    }
                    Flow {
                        width: parent.width
                        height: childrenRect.height
                        spacing: 12
                        StoneButton { label: "Play"; emphasized: true; width: 100; height: 40; onActivated: detail.appBridge.openLibraryOwner(detail.item.owner) }
                        StoneButton { label: "Show in Folder"; width: 166; height: 40; onActivated: detail.appBridge.openLibraryFolder(detail.item.owner) }
                        StoneButton { label: "⋯"; accessibilityLabel: "More actions"; width: 44; height: 40; onActivated: detail.actionsRequested(detail.item.owner) }
                    }
                }
            }
            Column {
                visible: (detail.item.versions || []).length > 1
                width: parent.width
                spacing: 6
                Text { text: "Saved version"; color: theme.muted; font.pixelSize: 13 }
                Flow {
                    width: parent.width; spacing: 8
                    Repeater {
                        model: detail.item.versions || []
                        StoneButton {
                            required property var modelData
                            label: modelData.label
                            selected: modelData.owner === detail.item.owner
                            size: "inline"
                            width: Math.min(380, implicitWidth)
                            onActivated: detail.appBridge.chooseLibraryVersion(modelData.owner)
                        }
                    }
                }
            }
            Flow {
                id: annotationRow
                width: parent.width
                height: childrenRect.height
                spacing: 16
                StoneField {
                    id: descriptionPanel
                    objectName: "libraryDescriptionPanel"
                    property bool editing: false
                    width: detail.compact ? annotationRow.width : Math.round(annotationRow.width * 0.62)
                    height: editing ? 220 : 184
                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        Text {
                            objectName: "libraryDescriptionHeading"
                            text: detail.item.userDescription ? "Your description" : "Source description"
                            color: theme.text; font.pixelSize: 20
                        }
                        ScrollView {
                            id: descriptionScroll
                            objectName: "libraryDescriptionScroll"
                            visible: !descriptionPanel.editing
                            width: parent.width
                            height: 78
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            Text {
                                objectName: "libraryDescriptionText"
                                text: detail.item.description || ""
                                width: descriptionScroll.availableWidth
                                color: theme.muted
                                font.pixelSize: 14
                                wrapMode: Text.WordWrap
                            }
                        }
                        StoneField {
                            visible: descriptionPanel.editing
                            width: parent.width; height: 116
                            TextArea {
                                id: descriptionEditor
                                anchors.fill: parent; anchors.margins: 10
                                padding: 0; wrapMode: TextEdit.Wrap
                                color: theme.text; font.pixelSize: 14; background: Item {}
                            }
                        }
                        Row {
                            spacing: 8
                            StoneButton {
                                label: descriptionPanel.editing ? "Save" : "Edit description"
                                size: "inline"
                                width: descriptionPanel.editing ? 70 : 150
                                onActivated: {
                                    if (!descriptionPanel.editing) {
                                        descriptionEditor.text = detail.item.descriptionInput || ""
                                        descriptionPanel.editing = true
                                    } else if (detail.appBridge.saveLibraryDescription(detail.item.owner, descriptionEditor.text)) {
                                        descriptionPanel.editing = false
                                    }
                                }
                            }
                            StoneButton {
                                visible: descriptionPanel.editing
                                label: "Cancel"; size: "inline"; width: 75
                                onActivated: descriptionPanel.editing = false
                            }
                        }
                    }
                }
                StoneField {
                    width: detail.compact ? annotationRow.width : annotationRow.width - Math.round(annotationRow.width * 0.62) - 16
                    height: Math.max(150, tagColumn.childrenRect.height + 32)
                    Column {
                        id: tagColumn
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 9
                        Text { text: "Tags and notes"; color: theme.text; font.pixelSize: 20 }
                        Flow {
                            width: parent.width
                            spacing: 6
                            Repeater {
                                model: detail.item.tags || []
                                StoneButton {
                                    required property string modelData
                                    label: modelData + " ×"
                                    accessibilityLabel: "Remove tag " + modelData
                                    size: "inline"
                                    width: Math.min(tagColumn.width, implicitWidth)
                                    onActivated: detail.appBridge.editLibraryTag(detail.item.owner, modelData, true)
                                }
                            }
                        }
                        Row {
                            width: parent.width; spacing: 8
                            StoneField {
                                width: Math.max(80, parent.width - 66); height: 34
                                TextField {
                                    id: detailTagInput
                                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10
                                    padding: 0; verticalAlignment: TextInput.AlignVCenter
                                    placeholderText: "Add a tag…"
                                    color: theme.text; placeholderTextColor: theme.muted
                                    font.pixelSize: 13; background: Item {}
                                    onAccepted: {
                                        if (detail.appBridge.editLibraryTag(detail.item.owner, text, false)) text = ""
                                    }
                                }
                            }
                            StoneButton {
                                label: "+"; accessibilityLabel: "Add tag"
                                size: "inline"; width: 50; height: 34
                                onActivated: {
                                    if (detail.appBridge.editLibraryTag(detail.item.owner, detailTagInput.text, false)) detailTagInput.text = ""
                                }
                            }
                        }
                        Text { text: detail.item.note || ""; width: parent.width; color: theme.muted; font.pixelSize: 13; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
                        StoneButton { label: "Edit organization"; size: "inline"; width: 155; onActivated: detail.annotationRequested(detail.item.owner) }
                    }
                }
            }
            Flow {
                id: factsRow
                width: parent.width
                height: childrenRect.height
                spacing: 16
                Repeater {
                    model: [
                        { title: "Source Details", fields: detail.item.source || [] },
                        { title: "Output Details", fields: detail.item.output || [] }
                    ]
                    StoneField {
                        id: factsPanel
                        required property var modelData
                        readonly property string section: modelData.title === "Source Details" ? "source" : "output"
                        width: detail.compact ? factsRow.width : (factsRow.width - 16) / 2
                        height: factsColumn.childrenRect.height + 34
                        Column {
                            id: factsColumn
                            x: 17
                            y: 17
                            width: parent.width - 34
                            spacing: 11
                            Text { text: modelData.title; color: theme.text; font.pixelSize: 20 }
                            Rectangle { width: parent.width; height: 1; color: theme.border }
                            Repeater {
                                model: modelData.fields
                                Row {
                                    required property var modelData
                                    width: factsColumn.width
                                    spacing: 12
                                    Text { text: modelData.label; width: Math.min(138, parent.width * 0.29); color: theme.muted; font.pixelSize: 14; wrapMode: Text.WordWrap }
                                    Text {
                                        text: modelData.value
                                        width: parent.width - Math.min(138, parent.width * 0.29) - 12 - (modelData.label === "Saved Location" ? 46 : 0)
                                        color: modelData.label === "Source URL" ? theme.accent : theme.text
                                        font.pixelSize: 14; wrapMode: Text.WrapAnywhere
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: {
                                                if (modelData.label === "Source URL") detail.appBridge.openLibrarySource(detail.item.owner)
                                                else detail.appBridge.copyLibraryFact(
                                                    detail.item.owner,
                                                    factsPanel.section,
                                                    modelData.label)
                                            }
                                        }
                                    }
                                    StoneButton {
                                        visible: modelData.label === "Saved Location"
                                        label: "⧉"
                                        accessibilityLabel: "Copy saved location"
                                        size: "inline"
                                        width: visible ? 34 : 0
                                        height: 30
                                        onActivated: detail.appBridge.copyLibraryFact(detail.item.owner, "output", "Saved Location")
                                    }
                                }
                            }
                        }
                    }
                }
            }
            Item { width: 1; height: 20 }
        }
    }
}
