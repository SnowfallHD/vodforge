import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: deck
    RunStatusTone { id: runStatusTone }
    property var appBridge
    property bool compact: false
    readonly property var projection: appBridge.runDeck
    readonly property var visibleRecords: projection.visible || []
    signal openSaved(string owner)
    signal removeSaved(string owner)
    function showActions(record) {
        if (record.kind === "active" &&
                !deck.appBridge.admitRunMenu(record.runId, record.executionToken || ""))
            return
        selectedRecord = record
        actionsPopup.open()
    }
    function openActiveActions() {
        for (let record of projection.records || []) {
            if (record.kind === "active") {
                showActions(record)
                return
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8
        RowLayout {
            Layout.fillWidth: true
            Text { text: "RUN DECK"; color: theme.muted; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
            StoneButton {
                id: allRunsButton
                objectName: "allRunsButton"
                visible: deck.projection.count > 0
                label: "All " + deck.projection.count + " runs"
                size: "inline"
                Layout.preferredWidth: 120
                onHoveredChanged: {
                    if (hovered) {
                        hoverClose.stop()
                        allRunsPopup.open()
                    } else if (allRunsPopup.visible) hoverClose.restart()
                }
                onActivated: {
                    allRunsPopup.close()
                    deck.appBridge.select("Library")
                }
                onVisibleChanged: { if (!visible) allRunsPopup.close() }
            }
        }
        StoneField {
            Layout.fillWidth: true
            Layout.preferredHeight: deck.compact ? 64 : 88
            RowLayout {
                anchors.fill: parent
                anchors.margins: 9
                spacing: 8
                Text {
                    visible: deck.visibleRecords.length === 0
                    text: "Your runs will collect here. Start with a URL above."
                    color: theme.muted
                    font.pixelSize: 14
                    Layout.fillWidth: true
                }
                Repeater {
                    model: deck.visibleRecords
                    StoneField {
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: deck.compact ? 50 : 68
                        TapHandler { onTapped: deck.appBridge.selectRunRecord(modelData.selectionKey) }
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 6
                            spacing: 7
                            Image {
                                source: modelData.artwork
                                visible: source.toString().length > 0
                                Layout.preferredWidth: visible ? (deck.compact ? 48 : 61) : 0
                                Layout.preferredHeight: deck.compact ? 36 : 48
                                fillMode: Image.PreserveAspectCrop
                                smooth: true
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                Text { text: modelData.title; color: theme.text; font.pixelSize: 13; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text {
                                    objectName: "runDeckStatus"
                                    text: modelData.status
                                    color: runStatusTone.colorFor(modelData.kind,
                                                                  modelData.phase === "failed" ? "Failed" : modelData.status,
                                                                  theme)
                                    font.pixelSize: 12
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                RunProgress {
                                    visible: modelData.kind === "active"
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: visible ? 3 : 0
                                    kind: modelData.kind
                                    status: modelData.status
                                    progress: modelData.progress
                                }
                            }
                            StoneButton {
                                label: "⋯"
                                accessibilityLabel: "Actions for " + modelData.title
                                size: "inline"
                                Layout.preferredWidth: 31
                                onActivated: deck.showActions(modelData)
                            }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: deck.projection.summary; color: theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
            Text { text: "Runs process one at a time"; color: theme.muted; font.pixelSize: 12 }
        }
    }

    property var selectedRecord: ({})
    Popup {
        id: actionsPopup
        objectName: "runActionsPopup"
        x: Math.max(0, deck.width - width)
        y: deck.height - height - 40
        width: 225
        padding: 10
        modal: true
        onClosed: deck.appBridge.retireRunMenu()
        background: StoneField {}
        ColumnLayout {
            spacing: 6
            StoneButton {
                visible: deck.selectedRecord.kind === "active"
                label: "Cancel run"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.controlRun(deck.selectedRecord.runId, "cancel"); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "active"
                label: "Skip current item"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.controlRun(deck.selectedRecord.runId, "skip_item"); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "active"
                label: "Skip current source URL"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.controlRun(deck.selectedRecord.runId, "skip_source"); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "queued"
                label: "Remove from queue"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.removeQueued(deck.selectedRecord.runId); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "terminal"
                label: "Retry run"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.retryTerminal(deck.selectedRecord.runId); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "completed"
                label: "View in Library"
                Layout.fillWidth: true
                onActivated: { deck.openSaved(deck.selectedRecord.owner); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "completed"
                label: "Open saved location"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.openLibraryFolder(deck.selectedRecord.owner); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "completed" && deck.selectedRecord.hasYoutubeUrl
                label: "Copy YouTube URL"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.copySavedYoutubeUrl(deck.selectedRecord.owner); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "completed"
                label: "Remove from Library…"
                Layout.fillWidth: true
                onActivated: { deck.removeSaved(deck.selectedRecord.owner); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "preview"
                label: "Start download"
                Layout.fillWidth: true
                onActivated: {
                    if (deck.appBridge.openPreviewOwner(deck.selectedRecord.owner)) deck.appBridge.startPreviewDownload()
                    actionsPopup.close()
                }
            }
            StoneButton {
                label: "View Activity"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.select("Activity"); actionsPopup.close() }
            }
        }
    }
    Popup {
        id: allRunsPopup
        objectName: "allRunsPopup"
        parent: deck
        readonly property point anchor: allRunsButton.mapToItem(deck, 0, 0)
        x: Math.max(0, Math.min(deck.width - width, anchor.x + allRunsButton.width - width))
        y: anchor.y - height
        width: Math.min(440, deck.width)
        height: Math.min(285, Math.max(80, deck.projection.count * 42 + 18))
        padding: 9
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: StoneField {}
        ScrollView {
            anchors.fill: parent
            clip: true
            HoverHandler {
                id: popupHover
                onHoveredChanged: {
                    if (hovered) hoverClose.stop()
                    else if (allRunsPopup.visible) hoverClose.restart()
                }
            }
            Column {
                width: parent.width
                spacing: 3
                Repeater {
                    model: deck.projection.records || []
                    StoneButton {
                        required property var modelData
                        label: modelData.title + "  —  " + modelData.status
                        width: parent.width
                        height: 36
                        size: "inline"
                        onActivated: {
                            if (modelData.kind === "preview") deck.appBridge.openPreviewOwner(modelData.owner)
                            else deck.appBridge.selectRunRecord(modelData.selectionKey)
                            allRunsPopup.close()
                        }
                    }
                }
            }
        }
    }
    Timer {
        id: hoverClose
        interval: 100
        onTriggered: {
            if (!allRunsButton.hovered && !popupHover.hovered) allRunsPopup.close()
        }
    }
}
