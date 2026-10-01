import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs

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
    Timer {
        id: revealManualTimer
        interval: 50
        onTriggered: {
            if (!issueManualSettings.visible)
                return
            const viewport = issuePanel.contentItem
            const manualTop = issueManualSettings.y + issueContent.y
            const target = manualTop - viewport.height * 0.45
            viewport.contentY = Math.max(0, Math.min(target,
                viewport.contentHeight - viewport.height))
        }
    }

    Text {
        id: eyebrow
        objectName: "libraryFolderInspectorHeading"
        text: inspector.item.folder ? "CURRENT FOLDER" : "SELECTED ITEM"
        color: theme.muted
        font.pixelSize: 12
        font.bold: true
    }
    Item {
        id: overview
        objectName: "libraryFolderOverview"
        width: parent.width
        height: inspector.item.folder ? 214 : Math.max(81, selectedOverview.implicitHeight + 8)
        StoneField {
            objectName: "libraryFolderArtworkFrame"
            visible: !inspector.item.folder
            width: 124; height: 70
            ArtworkImage {
                anchors.fill: parent
                source: inspector.item.artwork || ""
            }
        }
        SceneIcon {
            objectName: "libraryFolderOverviewFallbackIcon"
            x: inspector.item.folder ? (parent.width - width) / 2 : 45
            y: inspector.item.folder ? 12 : 18
            width: inspector.item.folder ? 112 : 34
            height: width
            name: inspector.item.file ? "file" : inspector.item.folder ? "folder-solid" : "folder"
            visible: !(inspector.item.artwork || "")
        }
        Column {
            id: selectedOverview
            x: inspector.item.folder ? 0 : 136
            y: inspector.item.folder ? 136 : 0
            width: inspector.item.folder ? parent.width : Math.max(130, inspector.width - 136)
            spacing: 4
            Text {
                objectName: "libraryFolderSelectedTitle"
                text: inspector.item.title || "Choose a saved item to inspect its metadata."
                color: theme.text
                font.pixelSize: inspector.item.folder ? 20 : 15
                horizontalAlignment: inspector.item.folder ? Text.AlignHCenter : Text.AlignLeft
                font.bold: true
                width: parent.width
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Text {
                visible: !inspector.item.folder
                text: [inspector.item.creator, inspector.item.type].filter(Boolean).join("  ·  ")
                color: theme.muted
                font.pixelSize: 12
                width: parent.width
                elide: Text.ElideRight
            }
            Text {
                objectName: "libraryFolderSelectedLocation"
                horizontalAlignment: inspector.item.folder ? Text.AlignHCenter : Text.AlignLeft
                text: inspector.item.location || ""
                color: theme.muted
                font.pixelSize: 12
                width: parent.width
                elide: Text.ElideRight
                HoverHandler { id: selectedLocationHover }
                ToolTip.visible: selectedLocationHover.hovered && !!text
                ToolTip.text: text
            }
            Text {
                objectName: "libraryFolderSelectedSummary"
                visible: !inspector.item.folder && !!text
                text: [inspector.item.status, inspector.item.modeLabel].filter(Boolean).join("  ·  ")
                color: theme.muted
                font.pixelSize: 12
                width: parent.width
                wrapMode: Text.WordWrap
            }
        }
    }
    StoneButton {
        id: openCurrentFolder
        objectName: "libraryFolderOpenLocationButton"
        visible: inspector.appBridge.libraryFolders.mode === "folders"
                 && !!inspector.appBridge.libraryFolders.path
        label: "Open this folder"
        width: parent.width; height: 40
        onActivated: inspector.appBridge.openLibraryCurrentFolder()
    }
    StoneField {
        visible: !!inspector.item.folder
        width: parent.width
        height: folderContents.implicitHeight + 24
        Column {
            id: folderContents
            x: 12; y: 12; width: parent.width - 24; spacing: 10
            Text {
                text: inspector.item.count + (inspector.item.count === 1 ? " item" : " items") + " in this folder"
                color: theme.text; font.pixelSize: 13
                width: parent.width; wrapMode: Text.WordWrap
            }
            Text {
                text: inspector.item.unavailableCount > 0 ?
                      inspector.item.unavailableCount +
                      (inspector.item.unavailableCount === 1 ? " saved file is missing from this folder." : " saved files are missing from this folder.") :
                      "Choose a folder to browse it, or select a file to see its details."
                color: theme.muted; font.pixelSize: 12
                width: parent.width; wrapMode: Text.WordWrap
            }
            StoneButton {
                objectName: "libraryFolderReviewMissingButton"
                visible: (inspector.item.unavailableItems || []).length > 0
                label: "Recover: " + ((inspector.item.unavailableItems || [])[0] || {}).title
                width: parent.width; height: 40
                onActivated: inspector.appBridge.openFolderMissingIssue(inspector.item.unavailableItems[0].owner)
            }
            StoneButton {
                visible: inspector.item.unavailableCount > 1
                label: "See all in Issues & Recovery"
                width: parent.width; height: 40
                onActivated: inspector.appBridge.navigateLibraryFolders("issues")
            }
        }
    }
    ScrollView {
        id: filePanel
        VerticalScrollChain { nestedScrollView: filePanel }
        objectName: "libraryFolderFileInspector"
        visible: !!inspector.item.file
        width: parent.width
        height: Math.max(0, inspector.height - eyebrow.height - overview.height
                         - openCurrentFolder.height - inspector.spacing * 4)
        contentHeight: fileContents.implicitHeight + 24
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        background: StoneField {}
        Column {
            id: fileContents
            x: 12; y: 12; width: filePanel.availableWidth - 24; spacing: 12
            Text {
                text: inspector.item.type || "File"
                color: theme.accent; font.pixelSize: 14; font.bold: true
            }
            Text {
                text: inspector.item.location || ""
                color: theme.muted; font.pixelSize: 12
                width: parent.width; wrapMode: Text.WrapAnywhere
            }
            StoneButton {
                objectName: "libraryFolderFileOpenLocation"
                label: "Open this location"
                width: parent.width; height: 40
                onActivated: inspector.appBridge.openSelectedFolderFileLocation()
            }
            Text {
                visible: !!inspector.item.isMetadata
                text: "LIBRARY TAGS & DESCRIPTION"
                color: theme.accent; font.pixelSize: 12; font.bold: true
            }
            Text {
                visible: !!inspector.item.isMetadata
                text: "These edits are saved with this Library item."
                color: theme.muted; font.pixelSize: 12
                width: parent.width; wrapMode: Text.WordWrap
            }
            Text {
                visible: !!inspector.item.isMetadata
                text: "Tags"
                color: theme.muted; font.pixelSize: 12
            }
            StoneField {
                visible: !!inspector.item.isMetadata
                width: parent.width; height: 42
                TextField {
                    id: fileTags
                    objectName: "libraryFolderFileTags"
                    anchors.fill: parent; anchors.margins: 8
                    text: (inspector.item.tags || []).join(", ")
                    placeholderText: "Separate tags with commas"
                    color: theme.text; placeholderTextColor: theme.muted
                    background: Item {}
                }
            }
            Text {
                visible: !!inspector.item.isMetadata
                text: "Description"
                color: theme.muted; font.pixelSize: 12
            }
            StoneField {
                visible: !!inspector.item.isMetadata
                width: parent.width; height: 140
                TextArea {
                    id: fileDescription
                    objectName: "libraryFolderFileDescription"
                    anchors.fill: parent; anchors.margins: 8
                    text: inspector.item.description || ""
                    wrapMode: TextEdit.Wrap
                    color: theme.text
                    background: Item {}
                }
            }
            StoneButton {
                objectName: "libraryFolderFileSaveMetadata"
                visible: !!inspector.item.isMetadata
                label: "Save tags and description"
                width: parent.width; height: 40
                onActivated: inspector.appBridge.saveSelectedFolderMetadata(
                    inspector.item.associatedOwner, fileDescription.text, fileTags.text)
            }
        }
    }
    ScrollView {
        id: issuePanel
        VerticalScrollChain { nestedScrollView: issuePanel }
        objectName: "libraryIssueInspector"
        visible: !!inspector.item.issue
        width: parent.width
        height: Math.max(0, inspector.height - eyebrow.height - overview.height - inspector.spacing * 3)
        contentHeight: issueContent.implicitHeight + 20
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        background: StoneField {}
        Column {
            id: issueContent
            width: issuePanel.availableWidth - 20
            x: 10; y: 10
            spacing: 10
            Row {
                width: parent.width
                spacing: 10
                Text {
                    text: inspector.item.missing ? "FILE STATUS" : "RUN STATUS"
                    color: theme.muted
                    font.pixelSize: 12
                    font.bold: true
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: inspector.item.status || "Interrupted"
                    color: theme.accent
                    font.pixelSize: 15
                    font.bold: true
                }
            }
            Text {
                visible: !!inspector.item.missing
                text: inspector.issueSettings.source_editable
                      ? "The saved file was not found. Choose its source and download settings, or find the moved file."
                      : "The saved file was not found at its recorded location. Find the moved file or download it again."
                color: theme.muted; font.pixelSize: 12
                width: parent.width; wrapMode: Text.WordWrap
            }
            Text {
                visible: !!inspector.item.missing
                text: inspector.item.location || ""
                color: theme.muted; font.pixelSize: 12
                width: parent.width; wrapMode: Text.WrapAnywhere
            }
            StoneButton {
                objectName: "libraryIssueFindMovedFile"
                visible: !!inspector.item.missing
                width: parent.width; height: 40
                label: "Find moved file…"
                onActivated: inspector.appBridge.requestMissingFileRelink()
            }
            Text { visible: !inspector.item.missing || inspector.item.canRedownload; text: "SOURCE VIDEO"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            Row {
                visible: (!inspector.item.missing || inspector.item.canRedownload)
                         && !inspector.issueSettings.source_editable
                width: parent.width
                spacing: 8
                Text {
                    text: inspector.item.source || "Source link unavailable"
                    color: theme.muted
                    width: parent.width - (copyIssueUrl.visible ? 42 : 0)
                    font.pixelSize: 12
                    elide: Text.ElideMiddle
                }
                StoneButton {
                    id: copyIssueUrl
                    visible: !!inspector.item.source
                    label: "⧉"; accessibilityLabel: "Copy source URL"; size: "inline"
                    width: visible ? 34 : 0; height: 30
                    onActivated: inspector.appBridge.copyIssueSource()
                }
            }
            StoneField {
                visible: (!inspector.item.missing || inspector.item.canRedownload)
                         && !!inspector.issueSettings.source_editable
                width: parent.width; height: 40
                TextField {
                    anchors.fill: parent; anchors.margins: 9; anchors.rightMargin: 47
                    placeholderText: "Paste source video URL"
                    text: inspector.item.source || ""
                    color: theme.text; placeholderTextColor: theme.muted
                    background: Item {}
                    onTextEdited: inspector.appBridge.setIssueRetrySource(text)
                    onAccepted: inspector.appBridge.setIssueRetrySource(text)
                }
                StoneButton {
                    anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                    anchors.rightMargin: 6
                    visible: !!inspector.item.source
                    label: "⧉"; accessibilityLabel: "Copy source URL"; size: "inline"
                    width: 34; height: 30
                    onActivated: inspector.appBridge.copyIssueSource()
                }
            }
            Rectangle {
                visible: !inspector.item.missing || inspector.item.canRedownload
                width: parent.width; height: 1
                color: theme.muted; opacity: 0.3
            }
            Text {
                objectName: "libraryIssueRetrySettingsHeading"
                text: "RETRY SETTINGS"
                visible: !inspector.item.missing || inspector.item.canRedownload
                color: theme.accent
                font.pixelSize: 12
                font.bold: true
            }
            Text { text: "Save to"; visible: !inspector.item.missing || inspector.item.canRedownload; color: theme.muted; font.pixelSize: 12; font.bold: true }
            StoneButton {
                objectName: "libraryIssueOutputFolder"
                visible: !inspector.item.missing || inspector.item.canRedownload
                width: parent.width; height: 40
                label: inspector.issueSettings.output_dir || "Choose output folder…"
                accessibilityLabel: "Choose output folder for this retry"
                ToolTip.visible: hovered && !!inspector.issueSettings.output_dir
                ToolTip.text: inspector.issueSettings.output_dir || ""
                onActivated: {
                    issueFolderDialog.currentFolder = inspector.issueSettings.output_url || ""
                    issueFolderDialog.open()
                }
            }
            Text { text: "Output"; visible: !inspector.item.missing || inspector.item.canRedownload; color: theme.muted; font.pixelSize: 12; font.bold: true }
            InlineSelector {
                objectName: "libraryIssueFormatSelector"
                visible: !inspector.item.missing || inspector.item.canRedownload
                enabled: !inspector.item.missing || !!inspector.issueSettings.source_editable
                buttonObjectName: "libraryIssueFormat"
                width: parent.width
                currentValue: inspector.issueSettings.output_type || ""
                buttonText: currentValue || "Choose output type…"
                options: [
                    {label: "MP4", value: "MP4"},
                    {label: "MP3", value: "MP3"},
                    {label: "Original audio", value: "Original audio"}
                ]
                onChosen: value => inspector.appBridge.setIssueRetrySetting("output_type", value)
            }
            Text { text: "Output mode"; visible: !inspector.item.missing || inspector.item.canRedownload; color: theme.muted; font.pixelSize: 12; font.bold: true }
            InlineSelector {
                objectName: "libraryIssueModeSelector"
                visible: !inspector.item.missing || inspector.item.canRedownload
                buttonObjectName: "libraryIssueMode"
                width: parent.width
                currentValue: inspector.issueSettings.export_mode || ""
                buttonText: currentValue ? inspector.item.modeLabel : "Choose output mode…"
                options: inspector.appBridge.exportModeOptions
                onChosen: value => {
                    inspector.appBridge.setIssueRetrySetting("export_mode", value)
                    if (value === "Manual Override")
                        revealManualTimer.restart()
                }
            }
            StoneField {
                id: issueManualSettings
                visible: (!inspector.item.missing || inspector.item.canRedownload)
                         && inspector.issueSettings.output_type === "MP4"
                         && inspector.issueSettings.export_mode === "Manual Override"
                width: parent.width
                height: manualControls.implicitHeight + 24
                Rectangle {
                    x: 10; y: 10
                    width: 3; height: parent.height - 20
                    radius: 1
                    color: theme.accent
                    opacity: 0.8
                }
                ManualMp4Settings {
                    id: manualControls
                    objectName: "libraryIssueManualMp4"
                    x: 22; y: 12
                    width: parent.width - 34
                    gridColumns: 1
                    backend: issueManualAdapter
                    colors: theme
                }
            }
            Text { text: "Quality ceiling"; visible: !inspector.item.missing || inspector.item.canRedownload; color: theme.muted; font.pixelSize: 12; font.bold: true }
            InlineSelector {
                objectName: "libraryIssueQualitySelector"
                visible: !inspector.item.missing || inspector.item.canRedownload
                buttonObjectName: "libraryIssueQuality"
                width: parent.width
                currentValue: inspector.issueSettings.quality || ""
                buttonText: currentValue || "Choose quality…"
                options: qualityOptions.map(function(value) { return {label: value, value: value} })
                onChosen: value => inspector.appBridge.setIssueRetrySetting("quality", value)
            }
            Rectangle {
                width: parent.width; height: 1
                color: theme.muted; opacity: 0.3
            }
            Column {
                id: issueOptionsSection
                visible: !inspector.item.missing || inspector.item.canRedownload
                width: parent.width
                property bool expanded: false
                spacing: 4
                StoneButton {
                    objectName: "libraryIssueOptions"
                    width: parent.width; height: 38
                    label: issueOptionsSection.expanded ? "Download options  ▴" : "Download options  ▾"
                    onActivated: issueOptionsSection.expanded = !issueOptionsSection.expanded
                }
                StoneField {
                    visible: issueOptionsSection.expanded
                    width: parent.width
                    height: optionRows.implicitHeight + 8
                    Column {
                        id: optionRows
                        x: 4; y: 4; width: parent.width - 8; spacing: 2
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
                                width: parent.width; height: 36
                                label: (inspector.issueSettings[modelData.key] ? "✓  " : "    ") + modelData.label
                                enabled: (!inspector.item.missing || modelData.key !== "single_video_only")
                                         && (modelData.key !== "use_nvenc" || inspector.appBridge.nvencAvailable
                                             || !!inspector.issueSettings.use_nvenc)
                                onActivated: inspector.appBridge.setIssueRetryFlag(modelData.key, !inspector.issueSettings[modelData.key])
                            }
                        }
                    }
                }
            }
            Rectangle {
                visible: !inspector.item.missing || inspector.item.canRedownload
                width: parent.width; height: 1
                color: theme.muted; opacity: 0.3
            }
            Text {
                text: "This retry uses the saved MP3 and YouTube access settings where available."
                visible: !inspector.item.missing || inspector.item.canRedownload
                width: parent.width; wrapMode: Text.WordWrap
                color: theme.muted; font.pixelSize: 12
            }
            StoneButton {
                objectName: "libraryIssueDownload"
                visible: !inspector.item.missing || inspector.item.canRedownload
                width: parent.width; height: 42
                label: "Download"
                emphasized: true
                enabled: inspector.item.missing ?
                         inspector.item.canRedownload && ["Queued", "Preparing", "Downloading", "Transcoding"].indexOf(inspector.item.status) < 0 :
                         ["Failed", "Stopped", "Skipped"].indexOf(inspector.item.status) >= 0
                onActivated: inspector.appBridge.downloadSelectedIssue()
            }
            Text {
                text: inspector.appBridge.status !== "Ready" ? inspector.appBridge.status : ""
                visible: text.length > 0
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
                (eyebrow.height + overview.height + openDetails.height + tabs.height
                 + (openCurrentFolder.visible ? openCurrentFolder.height + inspector.spacing : 0)
                 + inspector.spacing * 4))
        Item {
            anchors.fill: parent
            anchors.margins: 10
            visible: inspector.section === "Item"
            Column {
                id: itemColumn
                anchors.fill: parent
                spacing: 10
                Repeater {
                    model: (inspector.item.source || []).slice(0, 1).concat((inspector.item.output || []).slice(0, 1))
                    delegate: Text {
                        required property var modelData
                        width: itemColumn.width
                        text: modelData.label + ": " + modelData.value
                        color: theme.muted
                        font.pixelSize: 12
                        elide: Text.ElideRight
                        HoverHandler { id: factHover }
                        ToolTip.visible: factHover.hovered
                        ToolTip.text: text
                    }
                }
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
                    id: tagsScroll
                    VerticalScrollChain { nestedScrollView: tagsScroll }
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
                VerticalScrollChain { nestedScrollView: descriptionScroll }
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
