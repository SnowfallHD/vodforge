import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Window

Column {
    id: inspector
    objectName: "libraryFolderInspector"
    property var appBridge
    readonly property var item: appBridge.libraryFolderInspector
    readonly property var issueSettings: item.settings || ({})
    property string section: "Item"
    property real targetPanelBottom: height
    spacing: 8

    QtObject {
        id: issueManualAdapter
        property var manualValues: inspector.issueSettings.manual
                                   ? inspector.issueSettings.manual : inspector.appBridge.manualValues
        function setManualValue(key, value) {
            inspector.appBridge.setIssueManualValue(key, value)
        }
    }

    Text {
        id: eyebrow
        objectName: "libraryFolderInspectorHeading"
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
    ScrollView {
        id: issuePanel
        objectName: "libraryIssueInspector"
        visible: !!inspector.item.issue
        width: parent.width
        height: Math.max(0, inspector.height - eyebrow.height - overview.height - inspector.spacing * 3)
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        background: StoneField {}
        Column {
            width: issuePanel.availableWidth - 20
            x: 10; y: 10
            spacing: 9
            Text {
                text: inspector.item.status || "Interrupted"
                color: theme.accent
                font.pixelSize: 15
                font.bold: true
            }
            Text {
                visible: !inspector.issueSettings.source_editable
                text: inspector.item.source || "Source link unavailable"
                color: theme.muted
                width: parent.width
                font.pixelSize: 12
                elide: Text.ElideMiddle
            }
            StoneField {
                visible: !!inspector.issueSettings.source_editable
                width: parent.width; height: 40
                TextField {
                    anchors.fill: parent; anchors.margins: 9
                    placeholderText: "Paste source video URL"
                    text: inspector.item.source || ""
                    color: theme.text; placeholderTextColor: theme.muted
                    background: Item {}
                    onTextEdited: inspector.appBridge.setIssueRetrySource(text)
                    onAccepted: inspector.appBridge.setIssueRetrySource(text)
                }
            }
            Text { text: "Save to"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                objectName: "libraryIssueOutputFolder"
                width: parent.width; height: 40
                label: inspector.issueSettings.output_dir || "Choose output folder…"
                accessibilityLabel: "Choose output folder for this retry"
                onActivated: issueFolderDialog.open()
            }
            Text { text: "Output"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                id: issueFormatButton
                objectName: "libraryIssueFormat"
                width: parent.width; height: 38
                label: inspector.issueSettings.output_type || "Choose output type…"
                onActivated: { issueFormatMenu.anchorItem = issueFormatButton; issueFormatMenu.open() }
            }
            Text { text: "Output mode"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                id: issueModeButton
                objectName: "libraryIssueMode"
                width: parent.width; height: 38
                label: inspector.issueSettings.export_mode ? inspector.item.modeLabel : "Choose output mode…"
                onActivated: { issueModeMenu.anchorItem = issueModeButton; issueModeMenu.open() }
            }
            Text { text: "Quality ceiling"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                id: issueQualityButton
                objectName: "libraryIssueQuality"
                width: parent.width; height: 38
                label: inspector.issueSettings.quality || "Choose quality…"
                onActivated: { issueQualityMenu.anchorItem = issueQualityButton; issueQualityMenu.open() }
            }
            ManualMp4Settings {
                objectName: "libraryIssueManualMp4"
                visible: inspector.issueSettings.output_type === "MP4"
                         && inspector.issueSettings.export_mode === "Manual Override"
                width: parent.width
                gridColumns: 1
                backend: issueManualAdapter
                colors: theme
            }
            StoneButton {
                id: issueOptionsButton
                objectName: "libraryIssueOptions"
                width: parent.width; height: 38
                label: "Download options…"
                onActivated: { issueOptionsMenu.anchorItem = issueOptionsButton; issueOptionsMenu.open() }
            }
            Text {
                text: "This retry uses the saved MP3 and YouTube access settings where available."
                width: parent.width; wrapMode: Text.WordWrap
                color: theme.muted; font.pixelSize: 12
            }
            StoneButton {
                objectName: "libraryIssueDownload"
                width: parent.width; height: 42
                label: "Download"
                emphasized: true
                enabled: ["Failed", "Stopped", "Skipped"].indexOf(inspector.item.status) >= 0
                onActivated: inspector.appBridge.downloadSelectedIssue()
            }
            Text {
                text: inspector.appBridge.status || ""
                color: theme.muted; font.pixelSize: 12
                width: parent.width; wrapMode: Text.WordWrap
            }
        }
    }
    FolderDialog {
        id: issueFolderDialog
        title: "Choose output folder for this retry"
        onAccepted: inspector.appBridge.chooseIssueOutputUrl(selectedFolder)
    }
    AnchoredPopup {
        id: issueFormatMenu
        parent: inspector.Window.window ? inspector.Window.window.contentItem : inspector
        width: 215; height: 3 * 42 + 8; padding: 4
        background: StoneField {}
        Column {
            anchors.fill: parent; spacing: 2
            Repeater {
                model: ["MP4", "MP3", "Original audio"]
                StoneButton {
                    required property string modelData
                    width: parent.width; height: 40; label: modelData
                    selected: inspector.issueSettings.output_type === modelData
                    onActivated: { inspector.appBridge.setIssueRetrySetting("output_type", modelData); issueFormatMenu.close() }
                }
            }
        }
    }
    AnchoredPopup {
        id: issueModeMenu
        parent: inspector.Window.window ? inspector.Window.window.contentItem : inspector
        width: 230; height: inspector.appBridge.exportModeOptions.length * 42 + 8; padding: 4
        background: StoneField {}
        Column {
            anchors.fill: parent; spacing: 2
            Repeater {
                model: inspector.appBridge.exportModeOptions
                StoneButton {
                    required property var modelData
                    width: parent.width; height: 40; label: modelData.label
                    selected: inspector.issueSettings.export_mode === modelData.value
                    onActivated: { inspector.appBridge.setIssueRetrySetting("export_mode", modelData.value); issueModeMenu.close() }
                }
            }
        }
    }
    AnchoredPopup {
        id: issueQualityMenu
        parent: inspector.Window.window ? inspector.Window.window.contentItem : inspector
        width: 230; height: qualityOptions.length * 42 + 8; padding: 4
        background: StoneField {}
        Column {
            anchors.fill: parent; spacing: 2
            Repeater {
                model: qualityOptions
                StoneButton {
                    required property string modelData
                    width: parent.width; height: 40; label: modelData
                    selected: inspector.issueSettings.quality === modelData
                    onActivated: { inspector.appBridge.setIssueRetrySetting("quality", modelData); issueQualityMenu.close() }
                }
            }
        }
    }
    AnchoredPopup {
        id: issueOptionsMenu
        parent: inspector.Window.window ? inspector.Window.window.contentItem : inspector
        width: 245; height: 6 * 42 + 8; padding: 4
        background: StoneField {}
        Column {
            anchors.fill: parent; spacing: 2
            Repeater {
                model: [
                    { key: "single_video_only", label: "Single video only" },
                    { key: "use_nvenc", label: "NVIDIA encoder" },
                    { key: "embed_thumbnail", label: "Embed thumbnail" },
                    { key: "write_thumbnail", label: "Save thumbnail" },
                    { key: "embed_metadata", label: "Embed metadata" },
                    { key: "write_info_json", label: "Save metadata file" }
                ]
                StoneButton {
                    required property var modelData
                    width: parent.width; height: 40
                    label: (inspector.issueSettings[modelData.key] ? "✓  " : "    ") + modelData.label
                    enabled: modelData.key !== "use_nvenc" || inspector.appBridge.nvencAvailable
                             || !!inspector.issueSettings.use_nvenc
                    onActivated: inspector.appBridge.setIssueRetryFlag(modelData.key, !inspector.issueSettings[modelData.key])
                }
            }
        }
    }
    StoneButton {
        id: openDetails
        objectName: "libraryFolderOpenDetails"
        label: "Open details"
        width: parent.width; height: 40
        visible: !!inspector.item.owner
        enabled: !!inspector.item.owner
        onActivated: inspector.appBridge.openSelectedLibraryFolderDetail()
    }
    Row {
        id: tabs
        visible: !!inspector.item.owner
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
        visible: !!inspector.item.owner
        width: parent.width
        height: inspector.section === "Item" ? itemColumn.childrenRect.height + 20 :
            Math.max(360, inspector.targetPanelBottom -
                (eyebrow.height + overview.height + openDetails.height + tabs.height + inspector.spacing * 4))
        Item {
            anchors.fill: parent
            anchors.margins: 10
            visible: inspector.section === "Item"
            Column {
                id: itemColumn
                anchors.fill: parent
                spacing: 10
                Text { text: "Saved version"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Flow {
                    width: parent.width
                    height: childrenRect.height
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
                Row {
                    width: parent.width
                    Text { text: "Tags"; color: theme.muted; font.pixelSize: 12; font.bold: true; width: parent.width - 36 }
                    StoneButton {
                        label: "⧉"; accessibilityLabel: "Copy tags"; size: "inline"
                        width: 32; height: 24
                        onActivated: inspector.appBridge.copyLibraryText(inspector.item.owner, "tags")
                    }
                }
                ScrollView {
                    width: parent.width
                    height: Math.min(54, Math.max(18, tagsText.implicitHeight))
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    Text {
                        id: tagsText
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
            Row {
                width: parent.width
                Text {
                    objectName: "libraryFolderDescriptionHeading"
                    text: "DESCRIPTION"
                    color: theme.muted; font.pixelSize: 12; font.bold: true
                    width: parent.width - 36
                }
                StoneButton {
                    label: "⧉"; accessibilityLabel: "Copy description"; size: "inline"
                    width: 32; height: 24
                    onActivated: inspector.appBridge.copyLibraryText(inspector.item.owner, "description")
                }
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
