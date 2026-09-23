import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: deck
    property var appBridge
    property bool compact: false
    readonly property var projection: appBridge.runDeck
    readonly property var visibleRecords: projection.visible || []
    signal openSaved(string owner)
    function openActiveActions() {
        for (let record of projection.records || []) {
            if (record.kind === "active") {
                selectedRecord = record
                actionsPopup.open()
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
                visible: deck.projection.count > 0
                label: "All " + deck.projection.count + " runs"
                size: "inline"
                Layout.preferredWidth: 120
                onActivated: allRunsPopup.open()
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
                                Text { text: modelData.status; color: theme.muted; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                            }
                            StoneButton {
                                label: "⋯"
                                accessibilityLabel: "Actions for " + modelData.title
                                size: "inline"
                                Layout.preferredWidth: 31
                                onActivated: {
                                    deck.selectedRecord = modelData
                                    actionsPopup.open()
                                }
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
        x: Math.max(0, deck.width - width)
        y: Math.max(0, deck.height - height - 40)
        width: 225
        padding: 10
        modal: true
        background: StoneField {}
        ColumnLayout {
            spacing: 6
            StoneButton {
                visible: deck.selectedRecord.kind === "active"
                label: "Cancel run"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.cancel(); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "active"
                label: "Skip current item"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.skipItem(); actionsPopup.close() }
            }
            StoneButton {
                visible: deck.selectedRecord.kind === "active"
                label: "Skip current source URL"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.skipSource(); actionsPopup.close() }
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
                label: "View Activity"
                Layout.fillWidth: true
                onActivated: { deck.appBridge.select("Activity"); actionsPopup.close() }
            }
        }
    }
    Popup {
        id: allRunsPopup
        x: Math.max(0, deck.width - width)
        y: Math.max(0, deck.height - height - 40)
        width: Math.min(440, deck.width)
        height: Math.min(285, Math.max(80, deck.projection.count * 42 + 18))
        padding: 9
        modal: true
        background: StoneField {}
        ScrollView {
            anchors.fill: parent
            clip: true
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
                            if (modelData.kind === "completed") deck.openSaved(modelData.owner)
                            else deck.appBridge.select("Activity")
                            allRunsPopup.close()
                        }
                    }
                }
            }
        }
    }
}
