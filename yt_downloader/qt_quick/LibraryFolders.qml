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
        anchors.fill: parent
        spacing: 20
        ColumnLayout {
            Layout.preferredWidth: 184
            Layout.fillHeight: true
            spacing: 6
            Text { text: "BROWSE"; color: theme.muted; font.pixelSize: 12; font.bold: true }
            Repeater {
                model: [
                    { key: "folders", label: "Folders" },
                    { key: "all", label: "All media" },
                    { key: "activity", label: "Runs & previews" }
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
                text: "LOCATIONS"
                color: theme.muted; font.pixelSize: 12; font.bold: true
                Layout.topMargin: 18
            }
            Repeater {
                model: browser.model.locations || []
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
                label: "Back to Library"
                Layout.fillWidth: true
                onActivated: browser.appBridge.navigateLibrary("home")
            }
        }
        Rectangle { Layout.fillHeight: true; Layout.preferredWidth: 1; color: theme.border }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    label: "Up one folder"
                    Layout.preferredWidth: 150
                    enabled: browser.model.path.length > 0
                    onActivated: browser.appBridge.upLibraryFolder()
                }
                Text {
                    text: browser.model.path || "All locations"
                    color: theme.text; font.pixelSize: 17; elide: Text.ElideMiddle
                    Layout.fillWidth: true
                }
                StoneButton {
                    objectName: "libraryFolderRelinkButton"
                    visible: browser.model.mode === "folders" && !!browser.model.path
                    label: "Find this folder…"
                    size: "inline"
                    Layout.preferredWidth: 160
                    onActivated: browser.appBridge.requestFolderRelink(browser.model.path)
                }
                StoneButton {
                    objectName: "libraryFolderCompactDetails"
                    visible: !browser.showInspector
                    enabled: !!browser.appBridge.libraryFolderInspector.owner
                    label: "Selected details"
                    size: "inline"
                    Layout.preferredWidth: 145
                    onActivated: browser.appBridge.openSelectedLibraryFolderDetail()
                }
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
                                if (modelData.kind === "media")
                                    browser.appBridge.selectLibraryFolderComponent(modelData.key)
                                else browser.appBridge.openLibraryFolderComponent(modelData.key)
                            }
                            onDoubleActivated: browser.appBridge.openLibraryFolderComponent(modelData.key)
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 13
                                Text {
                                    text: modelData.kind === "folder" ? "▣" : modelData.kind === "activity" ? "◷" : "▶"
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
                        visible: (browser.model.highlights || []).length > 0
                        text: "RECENT EXPORTS"
                        color: theme.muted; font.pixelSize: 12; font.bold: true
                    }
                    Flow {
                        width: parent.width; spacing: 12
                        Repeater {
                            model: browser.model.highlights || []
                        StoneButton {
                            required property var modelData
                                width: Math.min(220, Math.max(150, (viewport.availableWidth - 36) / 4))
                                height: 126
                                label: ""
                                accessibilityLabel: modelData.title + ", " + modelData.detail
                            onActivated: browser.appBridge.selectLibraryFolderComponent(modelData.key)
                            onDoubleActivated: browser.appBridge.openLibraryFolderComponent(modelData.key)
                                Column {
                                    anchors.fill: parent; anchors.margins: 12; spacing: 9
                                    Text { text: modelData.title; color: theme.text; font.pixelSize: 15; font.bold: true; width: parent.width; elide: Text.ElideRight }
                                    Text { text: modelData.detail; color: theme.muted; font.pixelSize: 13; width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 3; elide: Text.ElideRight }
                                }
                            }
                        }
                    }
                    Text {
                        visible: browser.model.count === 0
                        text: "No saved media in this location."
                        color: theme.muted; font.pixelSize: 15
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: browser.model.count + " items · page " + (browser.model.page + 1) + " of " + browser.model.pages
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
}
