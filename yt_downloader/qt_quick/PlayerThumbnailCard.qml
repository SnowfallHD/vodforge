import QtQuick

StoneButton {
    id: card
    required property var modelData
    property var appBridge
    width: 207
    height: 142
    label: ""
    accessibilityLabel: "Play " + modelData.title
    onActivated: appBridge.playPlayerRelated(modelData.owner)
    ArtworkImage {
        x: card.artworkFaceInset
        y: card.artworkFaceInset
        width: card.width - card.artworkFaceInset * 2
        height: 112 - card.artworkFaceInset
        source: card.modelData.artwork || ""
        pending: source.toString().length === 0 && card.appBridge &&
            card.appBridge.sizedMediaArtworkState(card.modelData.owner, 244, 138) === "pending"
        inset: 0
    }
    Text {
        x: 9
        y: 117
        width: parent.width - 18
        text: card.modelData.title
        color: theme.text
        font.pixelSize: 13
        elide: Text.ElideRight
    }
}
