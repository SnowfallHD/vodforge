import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: deck
    property var appBridge
    property bool compact: false
    readonly property var projection: appBridge.runDeck
    // Keep the latest completed work in sight after the active slot finishes.
    readonly property var workRecords: (projection.records || []).filter(
        record => ["active", "queued", "completed", "terminal"].indexOf(record.kind) >= 0)
    readonly property var visibleRecords: workRecords.slice(0, 4)
    readonly property var allRunsRecords: workRecords.slice().sort((left, right) => {
        const priority = {active: 0, queued: 1, terminal: 2, completed: 3}
        return (priority[left.kind] ?? 4) - (priority[right.kind] ?? 4)
    })
    readonly property string workSummary: {
        if (workRecords.length === 0) return "No runs in progress"
        const parts = []
        for (const [kind, label] of [["active", "active"], ["queued", "queued"],
                                     ["completed", "completed"],
                                     ["terminal", "interrupted"]]) {
            const count = workRecords.filter(record => record.kind === kind).length
            if (count) parts.push(count + " " + label)
        }
        return workRecords.length + " run" + (workRecords.length === 1 ? "" : "s") +
               "  •  " + parts.join("  •  ")
    }
    function showActions(record, anchor) {
        if (record.kind === "active" &&
                !deck.appBridge.admitRunMenu(record.runId, record.executionToken || ""))
            return
        selectedRecord = record
        actionsPopup.anchorItem = anchor || allRunsButton
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
            id: deckHeader
            Layout.fillWidth: true
            Text { text: "RUN DECK"; color: theme.muted; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
            StoneButton {
                id: allRunsButton
                objectName: "allRunsButton"
                visible: deck.workRecords.length > 0
                label: "All " + deck.workRecords.length +
                       (deck.workRecords.length === 1 ? " run" : " runs")
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
                    deck.appBridge.select("Activity")
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
                    text: "Ready for a new run. Start with a URL above."
                    color: theme.muted
                    font.pixelSize: 14
                    Layout.fillWidth: true
                }
                Repeater {
                    // Keep the four visual slots alive while progress changes. A
                    // variant-list model replaces its delegates on every update,
                    // which also destroys an open menu's anchor.
                    model: Math.min(4, deck.workRecords.length)
                    RunDeckCard {
                        required property int index
                        record: deck.visibleRecords[index] || ({})
                        slotIndex: index
                        compact: deck.compact
                        visible: index < deck.visibleRecords.length
                        Layout.fillWidth: true
                        Layout.preferredHeight: deck.compact ? 50 : 68
                        onChosen: deck.appBridge.selectRunRecord(record.selectionKey)
                        onActionsRequested: function(anchor) { deck.showActions(record, anchor) }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: deck.workSummary; color: theme.muted; font.pixelSize: 12; Layout.fillWidth: true }
            Text { text: "Runs process one at a time"; color: theme.muted; font.pixelSize: 12 }
        }
    }

    property var selectedRecord: ({})
    AnchoredPopup {
        id: actionsPopup
        objectName: "runActionsPopup"
        parent: deck.parent
        preferAbove: true
        alignRight: true
        width: 225
        padding: 10
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
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
                label: "View Activity"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.select("Activity"); actionsPopup.close() }
            }
        }
    }
    AnchoredPopup {
        id: allRunsPopup
        objectName: "allRunsPopup"
        parent: deck.parent
        anchorItem: allRunsButton
        preferAbove: true
        alignRight: true
        overlap: 10
        width: Math.min(480, deck.width)
        height: Math.min(380, Math.max(84, deck.workRecords.length * 73 + 18))
        padding: 9
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: StoneField {}
        HoverHandler {
            id: popupHover
            objectName: "allRunsPopupHover"
            parent: allRunsPopup.contentItem
            onHoveredChanged: {
                if (hovered) hoverClose.stop()
                else if (allRunsPopup.visible) hoverClose.restart()
            }
        }
        ListView {
            id: allRunsList
            objectName: "allRunsScrollView"
            anchors.fill: parent
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            spacing: 5
            model: deck.allRunsRecords.length
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            delegate: RunDeckCard {
                required property int index
                objectName: "allRunsCard_" + index
                readonly property var displayedRecord: deck.allRunsRecords[index] || ({})
                record: displayedRecord
                artworkSource: displayedRecord.artwork ||
                    deck.appBridge.runDeckArtwork(displayedRecord.selectionKey || "")
                showActions: false
                width: allRunsList.width - 8
                height: 68
                onChosen: {
                    deck.appBridge.selectRunRecord(record.selectionKey)
                    allRunsPopup.close()
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
