import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: deck
    property var appBridge
    property bool compact: false
    readonly property var projection: appBridge.runDeck
    // Keep interrupted work visible even after newer runs complete.
    readonly property var workRecords: (projection.records || []).filter(
        record => ["active", "queued", "completed", "terminal"].indexOf(record.kind) >= 0)
    readonly property var allRunsRecords: workRecords.slice().sort((left, right) => {
        const priority = record => record.status === "Paused" ? 0.5 : ({active: 0, queued: 1, terminal: 2, completed: 3}[record.kind] ?? 4)
        return priority(left) - priority(right)
    })
    readonly property var visibleRecords: allRunsRecords.slice(0, 4)
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
        const trigger = anchor || allRunsButton
        if (actionsPopup.visible ||
                (actionsPopup.triggerItem === trigger && actionsPopup.dismissedByTriggerPress)) {
            actionsPopup.toggleFrom(trigger)
            return
        }
        if (record.kind === "active" &&
                !deck.appBridge.admitRunMenu(record.runId, record.executionToken || ""))
            return
        selectedRecord = record
        actionsPopup.anchorItem = trigger
        actionsPopup.toggleFrom(actionsPopup.anchorItem)
    }
    Connections {
        target: deck.appBridge
        function onRunDeckChanged() {
            if (!actionsPopup.visible || deck.selectedRecord.kind !== "active") return
            const current = (deck.projection.records || []).find(record =>
                record.kind === "active" && record.runId === deck.selectedRecord.runId &&
                record.executionToken === deck.selectedRecord.executionToken)
            if (!current) actionsPopup.close()
            else deck.selectedRecord = current
        }
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
            Text { text: "RUN DECK"; color: theme.muted; font.pixelSize: 12; font.bold: true; elide: Text.ElideRight; Layout.minimumWidth: 0; Layout.fillWidth: true }
            // This hover trigger has one held face. Pointer presses navigate;
            // they do not introduce StoneButton's separate click-face state.
            Item {
                id: allRunsButton
                objectName: "allRunsButton"
                visible: deck.workRecords.length > 0
                readonly property string label: "All " + deck.workRecords.length +
                       (deck.workRecords.length === 1 ? " run" : " runs")
                readonly property bool hovered: allRunsMouse.containsMouse
                readonly property bool held: hovered || allRunsPopup.visible
                signal activated()
                implicitHeight: buttonMetrics.inline.height
                Layout.preferredWidth: 120
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: label
                Accessible.focusable: true
                Accessible.focused: activeFocus
                Accessible.onPressAction: activated()
                Image {
                    objectName: "allRunsTriggerFace"
                    opacity: Window.window && Window.window.glassControlOpacity !== undefined
                             ? Window.window.glassControlOpacity : 1.0
                    anchors.fill: parent
                    source: "image://vodforge/button/" + Math.max(1, Math.round(parent.width))
                            + "/" + Math.max(1, Math.round(parent.height)) + "/"
                            + (allRunsButton.held ? "pressed" : "normal")
                            + "/0/r" + bridge.themeRevision
                    fillMode: Image.Stretch
                    smooth: true
                }
                Text {
                    anchors.centerIn: parent
                    text: allRunsButton.label
                    color: theme.text
                    font.family: buttonFontFamily
                    font.pixelSize: buttonMetrics.inline.fontPixels
                }
                MouseArea {
                    id: allRunsMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: allRunsButton.activated()
                }
                Keys.onReturnPressed: activated()
                Keys.onSpacePressed: activated()
                onHoveredChanged: {
                    if (hovered) {
                        hoverClose.stop()
                        allRunsPopup.triggerItem = allRunsButton; allRunsPopup.open()
                    } else if (allRunsPopup.visible) hoverClose.restart()
                }
                onActivated: {
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
                        artworkSource: record.artwork ||
                            deck.appBridge.runDeckArtwork(record.selectionKey || "")
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
            Text {
                id: summaryLabel
                text: deck.workSummary
                color: theme.muted
                font.pixelSize: 12
                // The aggregate line can exceed the remaining footer width.
                // Keep it in its own slot instead of painting over the policy.
                elide: Text.ElideRight
                Layout.minimumWidth: 0
                Layout.fillWidth: true
                Accessible.name: text
                LiquidToolTip { visible: parent.truncated && summaryHover.hovered; text: parent.text }
                HoverHandler { id: summaryHover }
            }
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
        onClosed: {
            deck.appBridge.retireRunMenu()
            if (allRunsPopup.visible) hoverClose.restart()
        }
        ColumnLayout {
            width: actionsPopup.availableWidth
            spacing: 6
            StoneButton {
                objectName: "deckControl0"
                property var action: deck.selectedRecord.kind === "active" ? ((deck.selectedRecord.controls || [])[0] || ({})) : ({})
                visible: !!action.label
                label: action.label || ""
                Accessible.description: action.description || ""
                LiquidToolTip { singleLine: true; visible: parent.hovered; text: parent.action.description || "" }
                Layout.fillWidth: true
                onActivated: {
                    deck.appBridge.controlRun(deck.selectedRecord.runId, action.operation)
                    actionsPopup.close()
                }
            }
            StoneButton {
                objectName: "deckControl1"
                property var action: deck.selectedRecord.kind === "active" ? ((deck.selectedRecord.controls || [])[1] || ({})) : ({})
                visible: !!action.label
                label: action.label || ""
                Accessible.description: action.description || ""
                LiquidToolTip { singleLine: true; visible: parent.hovered; text: parent.action.description || "" }
                Layout.fillWidth: true
                onActivated: {
                    deck.appBridge.controlRun(deck.selectedRecord.runId, action.operation)
                    actionsPopup.close()
                }
            }
            StoneButton {
                objectName: "deckControl2"
                property var action: deck.selectedRecord.kind === "active" ? ((deck.selectedRecord.controls || [])[2] || ({})) : ({})
                visible: !!action.label
                label: action.label || ""
                Accessible.description: action.description || ""
                LiquidToolTip { singleLine: true; visible: parent.hovered; text: parent.action.description || "" }
                Layout.fillWidth: true
                onActivated: {
                    deck.appBridge.controlRun(deck.selectedRecord.runId, action.operation)
                    actionsPopup.close()
                }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "queued"
                label: "Remove from queue"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.removeQueued(deck.selectedRecord.runId); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "terminal"
                objectName: "runResumeOrRetry"
                label: deck.selectedRecord.status === "Paused" ? "Resume" : "Retry run"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.retryTerminal(deck.selectedRecord.runId); actionsPopup.close() }
            }
            StoneButton {
                objectName: "runShowFolder"
                visible: deck.selectedRecord.kind === "terminal" && deck.appBridge.runHasSavedFile(deck.selectedRecord.runId || "")
                label: "Show in Folder"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.openRunFolder(deck.selectedRecord.runId); actionsPopup.close() }
            }
            StoneButton {
                objectName: "dismissTerminalRun"
                visible: deck.selectedRecord.kind === "terminal"
                label: "Remove"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.requestRunRemoval(deck.selectedRecord.runId); actionsPopup.close() }
            }
            StoneButton {
                objectName: "runOpenIssues"
                visible: deck.selectedRecord.kind === "terminal" || deck.selectedRecord.kind === "active"
                label: "Open Issues & Recovery"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.openRunIssues(deck.selectedRecord.runId); actionsPopup.close() }
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
        overlap: 0
        width: Math.min(480, deck.width)
        readonly property real desiredHeight: Math.min(380, Math.max(84, deck.workRecords.length * 73 + 18))
        height: desiredHeight
        // When neither side fits, shrink to the larger side rather than clamp
        // across the trigger. The ListView still exposes every run by scrolling.
        function reposition() {
            if (!visible || !anchorItem || !parent) return
            if (!anchorItem.visible) { close(); return }
            const point = anchorItem.mapToItem(parent, 0, 0)
            const above = Math.max(0, point.y)
            const below = Math.max(0, parent.height - point.y - anchorItem.height)
            const useAbove = above >= desiredHeight ||
                             (below < desiredHeight && above >= below)
            height = Math.min(desiredHeight, useAbove ? above : below)
            x = Math.max(0, Math.min(parent.width - width,
                                     point.x + anchorItem.width - width))
            y = useAbove ? point.y - height : point.y + anchorItem.height
        }
        padding: 9
        modal: false
        closePolicy: Popup.CloseOnEscape
        HoverHandler {
            id: popupHover
            objectName: "allRunsPopupHover"
            parent: allRunsPopup.contentItem.parent
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
                showActions: true
                width: allRunsList.width - 8
                height: 68
                onActionsRequested: function(anchor) { deck.showActions(record, anchor) }
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
            if (!actionsPopup.visible && !allRunsButton.hovered && !popupHover.hovered) allRunsPopup.close()
        }
    }
}
