import QtQuick

StoneButton {
    id: card
    property var appBridge
    property var projection
    property var group: ({})
    readonly property bool channel: group.kind === "channel"
    signal chosen()
    height: channel ? 82 : 161
    label: ""
    accessibilityLabel: (group.title || "") + ", " + (group.count || 0) + " saved item(s)"
    onActivated: chosen()
    ArtworkImage {
        id: artworkFrame
        objectName: "watchGroupArtworkImage"
        x: card.channel ? 8 : 0
        y: card.channel ? 9 : 0
        width: card.channel ? 64 : parent.width
        height: card.channel ? 64 : 108
        circular: card.channel
        cover: !card.channel
        inset: 0
        source: card.projection && card.appBridge && card.group.owner ?
                card.appBridge.watchGroupArtwork(card.group.owner, card.group.kind) : ""
    }
    Text {
        x: card.channel ? 82 : 9
        y: card.channel ? 20 : 113
        width: parent.width - x - 8
        text: card.group.title || ""
        color: theme.text
        font.pixelSize: 15
        font.bold: true
        elide: Text.ElideRight
    }
    Text {
        x: card.channel ? 82 : 9
        y: card.channel ? 44 : 137
        width: parent.width - x - 8
        text: (card.group.count || 0) + " saved"
        color: theme.muted
        font.pixelSize: 12
        elide: Text.ElideRight
    }
}
