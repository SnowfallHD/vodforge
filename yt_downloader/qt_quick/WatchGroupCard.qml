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
        x: card.channel ? card.artworkFaceInset + 1 : card.artworkFaceInset
        y: card.channel ? card.artworkFaceInset + 2 : card.artworkFaceInset
        width: card.channel ? 64 - (card.artworkFaceInset - 7) * 2 : parent.width - card.artworkFaceInset * 2
        height: card.channel ? width : 108 - card.artworkFaceInset
        circular: card.channel
        cover: !card.channel
        inset: 0
        source: {
            const revision = card.appBridge.artworkRevision
            return card.projection && card.group.owner ?
                card.appBridge.watchGroupArtwork(card.group.owner, card.group.kind) : ""
        }
        pending: source.toString().length === 0 && card.appBridge.artworkRevision >= 0 &&
            card.appBridge.groupArtworkState(card.group.owner, card.group.kind) === "pending"
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
