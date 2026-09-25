import QtQuick
import QtQuick.Effects

Item {
    id: artwork
    property url source: ""
    property bool circular: false
    property int inset: 4
    readonly property bool hasArtwork: source.toString().length > 0
    visible: hasArtwork

    Image {
        id: image
        anchors.fill: parent
        anchors.margins: artwork.inset
        source: artwork.source
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: !artwork.circular
    }
    Image {
        id: circularImage
        anchors.fill: parent
        anchors.margins: artwork.inset
        source: artwork.circular ? artwork.source : ""
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: artwork.circular
    }
    Rectangle {
        id: circleMask
        anchors.fill: circularImage
        radius: width / 2
        color: "white"
        visible: false
    }
    MultiEffect {
        anchors.fill: circularImage
        source: circularImage
        maskEnabled: true
        maskSource: circleMask
        visible: artwork.circular
    }
}
