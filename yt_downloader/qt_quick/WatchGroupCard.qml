import QtQuick

StoneButton {
    id: card
    property var appBridge
    property var projection
    property var group: ({})
    readonly property bool channel: group.kind === "channel"
    signal chosen()
    readonly property real channelScale: Math.max(1, Math.min(2, width / 260))
    readonly property real artworkHeight: Math.min(450, width * 9 / 16)
    height: channel ? 82 * channelScale : artworkHeight + 53
    label: ""
    accessibilityLabel: (group.title || "") + ", " + (group.count || 0) + " saved item(s)"
    onActivated: chosen()
    ArtworkImage {
        id: artworkFrame
        objectName: "watchGroupArtworkImage"
        x: card.channel ? (card.artworkFaceInset + 1) * card.channelScale : card.artworkFaceInset
        y: card.channel ? (card.artworkFaceInset + 2) * card.channelScale : card.artworkFaceInset
        width: card.channel ? (64 - (card.artworkFaceInset - 7) * 2) * card.channelScale : parent.width - card.artworkFaceInset * 2
        height: card.channel ? width : card.artworkHeight - card.artworkFaceInset
        circular: card.channel
        cover: false
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
        x: card.channel ? 82 * card.channelScale : 9
        y: card.channel ? 20 * card.channelScale : card.artworkHeight + 5
        width: parent.width - x - 8
        text: card.group.title || ""
        color: theme.text
        font.pixelSize: card.channel ? 15 * card.channelScale : 15
        font.bold: true
        elide: Text.ElideRight
    }
    Text {
        x: card.channel ? 82 * card.channelScale : 9
        y: card.channel ? 44 * card.channelScale : card.artworkHeight + 29
        width: parent.width - x - 8
        text: (card.group.count || 0) + " saved"
        color: theme.muted
        font.pixelSize: card.channel ? 12 * card.channelScale : 12
        elide: Text.ElideRight
    }
}
