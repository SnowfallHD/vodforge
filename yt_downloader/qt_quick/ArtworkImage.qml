import QtQuick

Item {
    id: artwork
    property url source: ""
    // Avatar assets arrive as transparent circular PNGs from QtArtwork.
    property bool circular: false
    property int inset: 4
    readonly property bool hasArtwork: source.toString().length > 0
    visible: hasArtwork

    Image {
        anchors.fill: parent
        anchors.margins: artwork.inset
        source: artwork.source
        fillMode: Image.PreserveAspectFit
        smooth: true
    }
}
