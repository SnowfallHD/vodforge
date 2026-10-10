import QtQuick
import QtQuick.Layouts

StoneField {
    id: card
    RunStatusTone { id: runStatusTone }
    property var record: ({})
    property string artworkSource: record.artwork || ""
    property bool compact: false
    property bool showActions: true
    property int slotIndex: -1
    signal chosen()
    signal actionsRequested(var anchor)

    interactive: true
    accessibilityLabel: (record.title || "Run") + ", " + (record.status || "")
    implicitHeight: compact ? 50 : 68
    onActivated: chosen()

    MouseArea {
        objectName: "runCardContextArea"
        anchors.fill: parent
        acceptedButtons: Qt.RightButton
        enabled: card.showActions
        onClicked: card.actionsRequested(card)
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 6
        spacing: 7
        Item {
            Layout.preferredWidth: card.compact ? 48 : 61
            Layout.preferredHeight: card.compact ? 36 : 48
            ArtworkImage {
                objectName: card.slotIndex >= 0 ? "runDeckArtwork_" + card.slotIndex : "allRunsArtwork"
                anchors.fill: parent
                visible: !!card.artworkSource
                source: card.artworkSource
                inset: 0
            }
            Image {
                objectName: card.slotIndex >= 0 ? "runDeckPlaceholder_" + card.slotIndex : "allRunsPlaceholder"
                anchors.centerIn: parent
                width: card.compact ? 32 : 40
                height: width
                visible: !card.artworkSource
                source: assetUrl + "brand/icon-180.png"
                fillMode: Image.PreserveAspectFit
                smooth: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 3
            Text {
                objectName: "runDeckCardTitle"
                text: card.record.title || ""
                color: theme.text
                font.pixelSize: 13
                font.bold: true
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            Text {
                objectName: "runDeckStatus"
                text: card.record.status || ""
                color: runStatusTone.colorFor(card.record.kind,
                                              card.record.phase === "failed" ? "Failed" : card.record.status,
                                              theme)
                font.pixelSize: 12
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
            RunProgress {
                visible: card.record.kind === "active"
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? 3 : 0
                kind: card.record.kind || ""
                status: card.record.status || ""
                progress: card.record.progress || 0
            }
        }
        StoneButton {
            id: actionButton
            visible: card.showActions
            objectName: card.slotIndex >= 0 ? "runDeckAction_" + card.slotIndex : "allRunsAction"
            label: "⋯"
            accessibilityLabel: "Actions for " + (card.record.title || "")
            size: "inline"
            Layout.preferredWidth: visible ? 31 : 0
            onActivated: card.actionsRequested(this)
        }
    }
}
