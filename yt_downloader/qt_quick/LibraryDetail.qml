import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import VODForge.Models 1.0

Item {
    id: detail
    property var appBridge
    signal actionsRequested(string owner, var anchor, var scrollViewport)
    signal annotationRequested(string owner)
    readonly property var item: appBridge.libraryDetail
    readonly property bool compact: width < 1020

    ScrollView {
        id: viewport
        objectName: "libraryDetailViewport"
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        Column {
            width: viewport.availableWidth
            spacing: 16
            StoneButton {
                label: "← Back"
                size: "inline"
                width: 72
                height: implicitHeight
                onActivated: detail.appBridge.backLibrary()
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
                        cover: true
                        inset: 0
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
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: detail.annotationRequested(detail.item.owner)
                        }
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
                        StoneButton { label: "⋯"; accessibilityLabel: "More actions"; width: 44; height: 40; onActivated: detail.actionsRequested(detail.item.owner, this, viewport) }
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
                    height: Math.max(editing ? 220 : 184, tagColumn.childrenRect.height + 32)
                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 8
                        Row {
                            width: parent.width
                            Text {
                                objectName: "libraryDescriptionHeading"
                                text: detail.item.userDescription ? "Your description" : "Source description"
                                color: theme.text; font.pixelSize: 20
                                width: parent.width - 44
                            }
                            CopyButton {
                                appBridge: detail.appBridge; owner: detail.item.owner || ""
                                field: "description"; accessibilityLabel: "Copy description"
                            }
                        }
                        ScrollView {
                            id: descriptionScroll
                            // Read-only TextEdit consumes navigation before ScrollView
                            // sees it. Keep modified text-selection shortcuts intact.
                            function scrollKey(event) {
                                const reverseSpace = event.key === Qt.Key_Space && event.modifiers === Qt.ShiftModifier
                                if (event.modifiers !== Qt.NoModifier && !reverseSpace) return
                                let direction = 0
                                let page = false
                                switch (event.key) {
                                case Qt.Key_Up: direction = -1; break
                                case Qt.Key_Down: direction = 1; break
                                case Qt.Key_PageUp: direction = -1; page = true; break
                                case Qt.Key_PageDown: direction = 1; page = true; break
                                case Qt.Key_Space: direction = reverseSpace ? -1 : 1; page = true; break
                                default: return
                                }
                                let view = contentItem
                                while (view && !(typeof view.contentY === "number" &&
                                        typeof view.contentHeight === "number" &&
                                        view.contentHeight > view.height)) view = view.parent
                                if (!view) return
                                const minimum = view.originY || 0
                                const maximum = minimum + Math.max(0, view.contentHeight - view.height)
                                const step = page ? Math.max(1, view.height * 0.9) : 32
                                view.contentY = Math.max(minimum, Math.min(maximum, view.contentY + direction * step))
                                event.accepted = true
                            }
                            Keys.onPressed: function(event) { scrollKey(event) }
                            VerticalScrollChain { nestedScrollView: descriptionScroll }
                            objectName: "libraryDescriptionScroll"
                            visible: !descriptionPanel.editing
                            width: parent.width
                            height: Math.max(78, descriptionPanel.height - 112)
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            SelectableText {
                                objectName: "libraryDescriptionText"
                                Keys.onPressed: function(event) { descriptionScroll.scrollKey(event) }
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
                    objectName: "libraryTagsNotesPanel"
                    width: detail.compact ? annotationRow.width : annotationRow.width - Math.round(annotationRow.width * 0.62) - 16
                    height: descriptionPanel.height
                    Column {
                        id: tagColumn
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 9
                        Row {
                            width: parent.width
                            Text { text: "Tags and notes"; color: theme.text; font.pixelSize: 20; width: parent.width - 44 }
                            CopyButton {
                                id: copyTagsButton
                                objectName: "libraryCopyTagsButton"
                                appBridge: detail.appBridge; owner: detail.item.owner || ""
                                field: "tags"; accessibilityLabel: "Copy tags to clipboard"
                                enabled: (detail.item.tags || []).length > 0
                            }
                        }
                        Flow {
                            width: parent.width
                            height: childrenRect.height
                            spacing: 6
                            readonly property var tagRows: (detail.item.tags || []).map(function(tag) { return {owner: tag, tag: tag} })
                            function updateTags() { tagWindow.replace(tagRows) }
                            onTagRowsChanged: Qt.callLater(updateTags)
                            OwnerWindowModel { id: tagWindow }
                            Repeater {
                                objectName: "libraryTagRepeater"
                                model: tagWindow
                                StoneButton {
                                    objectName: "libraryTagChip"
                                    required property var modelData
                                    label: modelData.tag + " ×"
                                    accessibilityLabel: "Remove tag " + modelData.tag
                                    hoverMaterial: false
                                    emphasized: hovered || activeFocus
                                    size: "inline"
                                    width: Math.min(tagColumn.width, implicitWidth)
                                    onActivated: detail.appBridge.editLibraryTag(detail.item.owner, modelData.tag, true)
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
                        Row {
                            width: parent.width
                            Text { text: "Your note"; color: theme.muted; font.pixelSize: 13; width: parent.width - 44 }
                            CopyButton {
                                id: copyNoteButton
                                objectName: "libraryCopyNoteButton"
                                appBridge: detail.appBridge; owner: detail.item.owner || ""
                                field: "note"; displayedText: noteInput.text
                                accessibilityLabel: "Copy displayed note to clipboard"
                                tooltipText: "Copy the displayed note without saving it"
                                enabled: noteInput.text.length > 0
                            }
                        }
                        StoneField {
                            width: parent.width; height: 68
                            TextArea {
                                id: noteInput
                                objectName: "libraryNoteInput"
                                property string owner: detail.item.owner || ""
                                onOwnerChanged: text = detail.item.note || ""
                                anchors.fill: parent; anchors.margins: 8
                                padding: 0; wrapMode: TextEdit.Wrap
                                text: detail.item.note || ""
                                placeholderText: "Add a note for yourself"
                                color: theme.text; placeholderTextColor: theme.muted
                                font.pixelSize: 13; background: Item {}
                            }
                        }
                        StoneButton {
                            label: "Save note"; size: "inline"; width: 92
                            onActivated: detail.appBridge.saveLibraryNote(detail.item.owner, noteInput.text)
                        }
                    }
                }
            }
            Flow {
                id: factsRow
                objectName: "libraryFactsRow"
                width: parent.width
                height: childrenRect.height
                spacing: 16
                property real commonHeight: 0
                function syncHeight() {
                    const source = factRepeater.itemAt(0)
                    const output = factRepeater.itemAt(1)
                    commonHeight = Math.max(source ? source.contentHeight : 0,
                                            output ? output.contentHeight : 0) + 34
                }
                Repeater {
                    id: factRepeater
                    onItemAdded: Qt.callLater(factsRow.syncHeight)
                    onItemRemoved: Qt.callLater(factsRow.syncHeight)
                    model: [
                        { title: "Source Details", fields: detail.item.source || [] },
                        { title: "Output Details", fields: detail.item.output || [] }
                    ]
                    StoneField {
                        id: factsPanel
                        required property var modelData
                        readonly property real contentHeight: factsColumn.childrenRect.height
                        onContentHeightChanged: Qt.callLater(factsRow.syncHeight)
                        readonly property string section: modelData.title === "Source Details" ? "source" : "output"
                        width: detail.compact ? factsRow.width : (factsRow.width - 16) / 2
                        height: detail.compact ? factsColumn.childrenRect.height + 34 : factsRow.commonHeight
                        Column {
                            id: factsColumn
                            x: 17
                            y: 17
                            width: parent.width - 34
                            spacing: 11
                            Text { text: modelData.title; color: theme.text; font.pixelSize: 20 }
                            Rectangle { width: parent.width; height: 1; color: theme.border }
                            Column {
                                width: parent.width
                                spacing: 0
                                Repeater {
                                    model: modelData.fields
                                    Row {
                                        required property var modelData
                                        objectName: "libraryFactRow_" + factsPanel.section + "_" + modelData.label
                                        width: factsColumn.width
                                        height: Math.max(30, factLabel.implicitHeight, factValue.implicitHeight)
                                        spacing: 12
                                        Text { id: factLabel; y: (parent.height - height) / 2; text: modelData.label; width: Math.min(138, parent.width * 0.29); color: theme.muted; font.pixelSize: 14; wrapMode: Text.WordWrap }
                                        SelectableText {
                                            id: factValue
                                            objectName: "libraryFactValue_" + factsPanel.section + "_" + modelData.label
                                            selectionEnabled: modelData.label !== "Source URL"
                                            y: (parent.height - height) / 2
                                            text: modelData.value
                                            width: parent.width - Math.min(138, parent.width * 0.29) - 12 -
                                                   (modelData.label === "Saved Location" || modelData.label === "Source URL" ? 46 : 0)
                                            color: modelData.label === "Source URL" ? theme.accent : theme.text
                                            font.pixelSize: 14; wrapMode: Text.WrapAnywhere
                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: modelData.label === "Source URL"
                                                cursorShape: Qt.PointingHandCursor
                                                onClicked: detail.appBridge.openLibrarySource(detail.item.owner)
                                            }
                                        }
                                        CopyButton {
                                            appBridge: detail.appBridge; owner: detail.item.owner || ""
                                            factLabel: modelData.label
                                            section: modelData.label === "Source URL" ? "source" : "output"
                                            visible: modelData.label === "Saved Location" || modelData.label === "Source URL"
                                            accessibilityLabel: modelData.label === "Source URL" ? "Copy source URL" : "Copy saved location"
                                            size: "inline"
                                            width: visible ? 34 : 0
                                            height: 30
                                            y: (parent.height - height) / 2
                                        }
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
