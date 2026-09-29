import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: browser
    objectName: "libraryFolderBrowser"
    property var appBridge
    readonly property var model: appBridge.libraryFolders
    readonly property bool showInspector: Window.window && Window.window.width >= 920 && Window.window.height >= 740

    RowLayout {
        objectName: "libraryFolderColumns"
        anchors.fill: parent
        anchors.topMargin: 12
        spacing: 20
        ColumnLayout {
            Layout.preferredWidth: 184
            Layout.fillHeight: true
            spacing: 6
            Text { objectName: "libraryFolderBrowseHeading"; text: "BROWSE"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            Repeater {
                model: [
                    { key: "folders", label: "My Files" },
                    { key: "all", label: "All media" },
                    { key: "issues", label: "Issues & Recovery" }
                ]
                StoneButton {
                    required property var modelData
                    label: modelData.label
                    selected: browser.model.mode === modelData.key
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onActivated: browser.appBridge.navigateLibraryFolders(modelData.key)
                }
            }
            Text {
                text: "SAVED LOCATIONS"
                visible: (browser.model.locations || []).length > 1
                color: theme.muted; font.pixelSize: 12; font.bold: true
                Layout.topMargin: 18
            }
            Repeater {
                model: (browser.model.locations || []).length > 1 ? browser.model.locations : []
                StoneButton {
                    required property var modelData
                    label: modelData.title
                    accessibilityLabel: modelData.title + ", " + modelData.detail
                    size: "inline"
                    Layout.fillWidth: true
                    onActivated: browser.appBridge.openLibraryFolderComponent(modelData.key)
                }
            }
            Item { Layout.fillHeight: true }
            StoneButton {
                label: "← Library"
                visible: browser.model.mode !== "folders"
                Layout.fillWidth: true
                onActivated: browser.appBridge.backLibrary()
            }
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: theme.border }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10
            RowLayout {
                objectName: "libraryFolderTopRow"
                Layout.fillWidth: true
                StoneButton {
                    objectName: "libraryFolderBackButton"
                    label: "← Back"
                    size: "inline"
                    Layout.preferredWidth: 72
                    visible: browser.model.mode === "folders"
                    onActivated: {
                        if (browser.model.canGoUp)
                            browser.appBridge.upLibraryFolder()
                        else
                            browser.appBridge.backLibrary()
                    }
                }
                Text {
                    objectName: "libraryFolderLocationHeading"
                    text: browser.model.mode === "issues" ? "Issues & Recovery" :
                          browser.model.mode === "all" ? "All media" : "My Files"
                    visible: browser.model.mode !== "folders"
                    color: theme.text; font.pixelSize: 17; elide: Text.ElideMiddle
                    Layout.fillWidth: true
                }
                StoneButton {
                    objectName: "libraryFolderCompactDetails"
                    visible: !browser.showInspector
                    enabled: !!browser.appBridge.libraryFolderInspector.owner
                             || !!browser.appBridge.libraryFolderInspector.issue
                             || !!browser.appBridge.libraryFolderInspector.file
                             || !!browser.appBridge.libraryFolderInspector.folder
                    label: browser.model.mode === "issues" ? "Selected issue" : "Selected details"
                    size: "inline"
                    Layout.preferredWidth: 145
                    onActivated: {
                        if (browser.model.mode === "issues"
                                || browser.appBridge.libraryFolderInspector.file
                                || browser.appBridge.libraryFolderInspector.folder)
                            compactIssuePopup.open()
                        else browser.appBridge.openSelectedLibraryFolderDetail()
                    }
                }
            }
            Flow {
                objectName: "libraryFolderBreadcrumbs"
                visible: browser.model.mode === "folders" && browser.model.breadcrumbs.length > 0
                Layout.fillWidth: true
                Layout.preferredHeight: implicitHeight
                spacing: 4
                Repeater {
                    model: browser.model.breadcrumbs || []
                    Row {
                        required property var modelData
                        spacing: 4
                        Text {
                            visible: modelData.key !== browser.model.breadcrumbs[0].key
                            text: "›"
                            color: theme.muted
                            font.pixelSize: 16
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        StoneButton {
                            objectName: "libraryFolderCrumb_" + modelData.key
                            label: modelData.label
                            accessibilityLabel: "Open " + modelData.label + " folder"
                            size: "inline"
                            selected: modelData.current
                            width: Math.min(160, implicitWidth)
                            onActivated: browser.appBridge.openLibraryBreadcrumb(modelData.key)
                        }
                    }
                }
            }
            Text {
                objectName: "libraryFolderActivityExplanation"
                visible: browser.model.mode === "issues"
                text: "Missing saved files and failed, stopped, or skipped runs are ready to recover here. Active retries stay until they finish. See every run in Forge's Run Deck."
                color: theme.muted
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            ScrollView {
                id: viewport
                objectName: "libraryFolderViewport"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Column {
                    objectName: "libraryFolderList"
                    width: viewport.availableWidth
                    spacing: 9
                    Repeater {
                        model: browser.model.components || []
                        StoneButton {
                            required property var modelData
                            objectName: "libraryFolderComponent_" + modelData.key
                            width: parent.width
                            height: 78
                            label: ""
                            selected: modelData.key === browser.model.selectedKey
                            accessibilityLabel: modelData.title + ", " + modelData.detail
                            onActivated: {
                                if (modelData.kind !== "folder")
                                    browser.appBridge.selectLibraryFolderComponent(modelData.key)
                                else browser.appBridge.openLibraryFolderComponent(modelData.key)
                            }
                            onDoubleActivated: {
                                if (browser.model.mode === "issues" || modelData.kind === "file")
                                    browser.appBridge.selectLibraryFolderComponent(modelData.key)
                                else browser.appBridge.openLibraryFolderComponent(modelData.key)
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 13
                                Text {
                                    text: modelData.kind === "folder" ? "▣" : modelData.kind === "file" ? "▤" : modelData.kind === "missing" ? "!" : modelData.kind === "activity" ? "◷" : "▶"
                                    color: theme.accent; font.pixelSize: 24
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: modelData.title; color: theme.text; font.pixelSize: 16; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: modelData.detail; color: theme.muted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                                }
                            }
                        }
                    }
                    Text {
                        objectName: "libraryFolderEmptyLabel"
                        visible: browser.model.count === 0
                        text: browser.model.mode === "issues" ?
                              browser.model.checkingAvailability ? "Checking saved files…" :
                              browser.model.availabilityError ? "Could not check saved files. Open Issues & Recovery again to retry." :
                              "Nothing needs recovery." :
                              browser.model.mode === "all" ? "No saved media yet." :
                              browser.model.checkingFolder ? "Opening folder…" :
                              browser.model.folderError ? "This folder could not be opened." :
                              "This folder is empty."
                        color: theme.muted; font.pixelSize: 15
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: browser.model.count + (browser.model.count === 1 ? " item" : " items") +
                          " · page " + (browser.model.page + 1) + " of " + browser.model.pages
                    color: theme.muted; font.pixelSize: 13
                    Layout.fillWidth: true
                }
                StoneButton {
                    label: "Previous"; size: "inline"; Layout.preferredWidth: 95
                    enabled: browser.model.page > 0
                    onActivated: browser.appBridge.pageLibraryFolder(-1)
                }
                StoneButton {
                    label: "Next"; size: "inline"; Layout.preferredWidth: 70
                    enabled: browser.model.page + 1 < browser.model.pages
                    onActivated: browser.appBridge.pageLibraryFolder(1)
                }
            }
        }
        Rectangle {
            visible: browser.showInspector
            Layout.fillHeight: true
            Layout.preferredWidth: visible ? 1 : 0
            color: theme.border
        }
        LibraryFolderInspector {
            id: selectedInspector
            visible: browser.showInspector
            Layout.preferredWidth: visible ? (browser.width + 40 < 1000 ? 350 : 380) : 0
            Layout.fillHeight: true
            targetPanelBottom: viewport.mapToItem(selectedInspector, 0, viewport.height).y
            appBridge: browser.appBridge
        }
    }
    Popup {
        id: compactIssuePopup
        objectName: "libraryCompactIssuePopup"
        parent: browser.Window.window ? browser.Window.window.contentItem : browser
        width: Math.min(420, parent.width - 24)
        height: Math.min(690, parent.height - 24)
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        modal: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: StoneField {}
        LibraryFolderInspector {
            anchors.fill: parent
            anchors.margins: 12
            appBridge: browser.appBridge
        }
    }
}
