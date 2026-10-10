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
    // Viewport geometry owns column widths; metadata must never widen a column.
    readonly property real inspectorColumnWidth: Math.min(680, Math.max(
        browser.width + 40 < 1000 ? 350 : 380, Math.round(browser.width * 0.34)))
    readonly property string navigationKey: model.mode + ":" + model.path
    property bool showFolderOpening: false
    readonly property bool checkingFolder: !!model.checkingFolder
    onCheckingFolderChanged: {
        showFolderOpening = false
        folderOpeningDelay.restart()
        if (!checkingFolder) folderOpeningDelay.stop()
    }
    onNavigationKeyChanged: {
        showFolderOpening = false
        folderOpeningDelay.restart()
        if (!checkingFolder) folderOpeningDelay.stop()
        if (viewport.contentItem) viewport.contentItem.contentY = 0
    }
    Timer {
        id: folderOpeningDelay
        interval: 300
        onTriggered: browser.showFolderOpening = browser.checkingFolder
    }

    RowLayout {
        objectName: "libraryFolderColumns"
        anchors.fill: parent
        anchors.topMargin: 12
        spacing: 20
        ColumnLayout {
            objectName: "libraryFolderNavigationColumn"
            Layout.minimumWidth: 184
            Layout.preferredWidth: 184
            Layout.maximumWidth: 184
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
                objectName: "libraryFolderLibraryButton"
                label: "← Library"
                Layout.fillWidth: true
                onActivated: browser.appBridge.backLibrary()
            }
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: theme.border }
        ColumnLayout {
            id: contentColumn
            objectName: "libraryFolderContentColumn"
            Layout.minimumWidth: 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10
            RowLayout {
                id: pathTrail
                objectName: "libraryFolderBreadcrumbs"
                visible: browser.model.mode === "folders" && (browser.model.breadcrumbs || []).length > 0
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: 32
                spacing: 2
                readonly property var crumbs: browser.model.breadcrumbs || []
                readonly property bool compact: width < 380
                readonly property bool collapsed: crumbs.length > (compact ? 2 : 3)
                readonly property var shown: !collapsed ? crumbs : compact ?
                                             [crumbs[0], crumbs[crumbs.length - 1]] :
                                             [crumbs[0], crumbs[crumbs.length - 2], crumbs[crumbs.length - 1]]
                onCompactChanged: ancestorsPopup.close()
                Repeater {
                    model: pathTrail.shown
                    RowLayout {
                        required property var modelData
                        required property int index
                        Layout.minimumWidth: modelData.current ? 60 : 0
                        Layout.preferredWidth: Math.min(140, crumb.implicitWidth)
                                               + (index > 0 ? 14 : 0)
                                               + (pathTrail.collapsed && index === 1 ? 54 : 0)
                        Layout.fillWidth: true
                        Layout.maximumWidth: modelData.current && pathTrail.crumbs.length > 1 ? 10000 : Layout.preferredWidth
                        spacing: 2
                        Text {
                            visible: index > 0
                            text: "›"; color: theme.muted; font.pixelSize: 13
                        }
                        StoneButton {
                            id: ancestorsButton
                            objectName: visible ? "libraryFolderAncestorsButton" : ""
                            visible: pathTrail.collapsed && index === 1
                            label: "…"
                            accessibilityLabel: "Show parent folders"
                            quiet: true
                            size: "inline"
                            Layout.preferredWidth: 36
                            onActivated: {
                                ancestorsPopup.anchorItem = ancestorsButton
                                ancestorsPopup.toggleFrom(ancestorsButton)
                            }
                        }
                        Text {
                            visible: ancestorsButton.visible
                            text: "›"; color: theme.muted; font.pixelSize: 13
                        }
                        StoneButton {
                            id: crumb
                            objectName: "libraryFolderCrumb_" + modelData.key
                            label: modelData.label
                            accessibilityLabel: (modelData.current ? "Current folder: " : "Open ") + modelData.label + (modelData.current ? "" : " folder")
                            quiet: true
                            size: "inline"
                            selected: modelData.current
                            interactive: !modelData.current
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.maximumWidth: modelData.current ? 10000 : 140
                            onActivated: browser.appBridge.openLibraryBreadcrumb(modelData.key)
                            LiquidToolTip { visible: parent.hovered; text: modelData.key }
                        }
                    }
                }
                Item { Layout.fillWidth: true; visible: pathTrail.crumbs.length === 1 }
            }
            RowLayout {
                objectName: "libraryFolderTopRow"
                Layout.fillWidth: true
                StoneButton {
                    objectName: "libraryFolderBackButton"
                    label: "←"
                    accessibilityLabel: "Parent folder"
                    enabled: browser.model.canGoUp && (browser.model.breadcrumbs || []).length > 1
                    size: "inline"
                    Layout.preferredWidth: 36
                    visible: browser.model.mode === "folders"
                    onActivated: {
                        if (enabled) browser.appBridge.upLibraryFolder()
                    }
                    LiquidToolTip { visible: parent.hovered; text: "Parent folder" }
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
                            compactIssuePopup.toggleFrom(this)
                        else browser.appBridge.openSelectedLibraryFolderDetail()
                    }
                }
            }
            Rectangle {
                visible: browser.model.mode === "folders"
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                Layout.topMargin: 4
                Layout.bottomMargin: 6
                color: theme.border
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
                Connections {
                    target: viewport.contentItem
                    function onContentYChanged() {
                        const view = viewport.contentItem
                        if (view.contentHeight > view.height
                                && view.contentY + view.height >= view.contentHeight - 170
                                && (browser.model.components || []).length < browser.model.count)
                            browser.appBridge.loadMoreLibraryFolder()
                    }
                }
                Column {
                    objectName: "libraryFolderList"
                    width: viewport.availableWidth
                    spacing: 9
                    Repeater {
                        model: browser.model.components || []
                        StoneButton {
                            required property var modelData
                            objectName: "libraryFolderComponent_" + modelData.key
                            doubleActivationEnabled: true
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
                            Keys.onDeletePressed: {
                                if (browser.model.mode === "issues" && browser.appBridge.selectLibraryFolderComponent(modelData.key))
                                    browser.appBridge.requestInspectorLibraryRemoval(modelData.key)
                            }
                            Keys.onPressed: event => {
                                if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && event.modifiers & Qt.ShiftModifier)) {
                                    if (browser.appBridge.selectLibraryFolderComponent(modelData.key)) {
                                        issueContext.anchorItem = parent
                                        issueContext.open()
                                        event.accepted = true
                                    }
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.RightButton
                                enabled: browser.model.mode === "issues"
                                onClicked: {
                                    if (browser.appBridge.selectLibraryFolderComponent(modelData.key)) {
                                        issueContext.anchorItem = parent
                                        issueContext.open()
                                    }
                                }
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 13
                                SceneIcon {
                                    visible: modelData.kind === "folder" || modelData.kind === "file"
                                    name: modelData.kind === "folder" ? "folder-solid" : "file"
                                    width: 28; height: 28
                                    Layout.preferredWidth: 28
                                    Layout.preferredHeight: 28
                                }
                                Text {
                                    visible: modelData.kind !== "folder" && modelData.kind !== "file"
                                    text: modelData.kind === "missing" ? "!" : modelData.kind === "activity" ? "◷" : "▶"
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
                                 && (!browser.checkingFolder || browser.showFolderOpening)
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
                    text: browser.model.count + (browser.model.count === 1 ? " item" : " items")
                    color: theme.muted; font.pixelSize: 13
                    Layout.fillWidth: true
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
            Layout.minimumHeight: 0
            Layout.preferredHeight: Math.max(0, browser.height - 12)
            Layout.maximumHeight: Math.max(0, browser.height - 12)
            visible: browser.showInspector
            Layout.minimumWidth: Layout.preferredWidth
            Layout.preferredWidth: visible ? browser.inspectorColumnWidth : 0
            Layout.maximumWidth: Layout.preferredWidth
            Layout.fillHeight: true
            // mapToItem does not bind to position changes of the mapped items.
            // Track their actual sibling/child positions through layout settlement.
            targetPanelBottom: contentColumn.y + viewport.y + viewport.height - selectedInspector.y
            appBridge: browser.appBridge
        }
    }
    AnchoredPopup {
        id: ancestorsPopup
        objectName: "libraryFolderAncestorsPopup"
        parent: browser.Window.window ? browser.Window.window.contentItem : browser
        width: Math.min(320, browser.width - 24)
        height: Math.min(300, ancestorList.implicitHeight + 16)
        padding: 8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        ScrollView {
            anchors.fill: parent
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                id: ancestorList
                width: ancestorsPopup.availableWidth
                spacing: 4
                Repeater {
                    model: pathTrail.crumbs.slice(1, pathTrail.compact ? -1 : -2)
                    StoneButton {
                        required property var modelData
                        objectName: "libraryFolderAncestor_" + modelData.key
                        label: modelData.label
                        accessibilityLabel: "Open " + modelData.label + " folder"
                        width: ancestorList.width
                        size: "inline"
                        onActivated: {
                            ancestorsPopup.close()
                            browser.appBridge.openLibraryBreadcrumb(modelData.key)
                        }
                    }
                }
            }
        }
        Connections {
            target: browser
            function onNavigationKeyChanged() { ancestorsPopup.close() }
        }
    }
    StonePopup {
        id: compactIssuePopup
        objectName: "libraryCompactIssuePopup"
        parent: browser.Window.window ? browser.Window.window.contentItem : browser
        width: Math.min(420, parent.width - 24)
        height: Math.min(690, parent.height - 24)
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        modal: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        LibraryFolderInspector {
            anchors.fill: parent
            anchors.margins: 12
            appBridge: browser.appBridge
        }
    }
    AnchoredPopup {
        id: issueContext
        objectName: "libraryIssueContextMenu"
        width: 180
        padding: 10
        property string capturedKey: ""
        onOpened: capturedKey = browser.model.selectedKey || ""
        Column {
            width: parent.width
            StoneButton {
                label: "Remove"
                width: parent.width
                onActivated: {
                    browser.appBridge.requestInspectorLibraryRemoval(issueContext.capturedKey)
                    issueContext.close()
                }
            }
        }
    }
}
