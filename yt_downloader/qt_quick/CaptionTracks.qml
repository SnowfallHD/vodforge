import QtQuick
import QtQuick.Controls

AnchoredPopup {
    id: menu
    required property var player
    signal trackRequested(int index)
    function trackLabel(index) {
        // QMediaMetaData::Language is key 6 in Qt's QML media metadata API.
        const language = player.subtitleTracks[index].stringValue(6)
        return language && language !== "Unknown"
            ? language + " · Track " + (index + 1)
            : "Caption track " + (index + 1)
    }
    preferAbove: true
    alignRight: true
    width: Math.min(245, parent.width - 24)
    height: Math.min(250, captionChoices.implicitHeight + topPadding + bottomPadding)
    padding: 5
    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: menu.availableWidth
        contentHeight: captionChoices.implicitHeight
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        Column {
            id: captionChoices
            width: menu.availableWidth
            spacing: 2
            StoneButton {
                width: parent.width; height: 40
                label: "Captions off"
                selected: !menu.player || menu.player.activeSubtitleTrack < 0
                onActivated: { menu.trackRequested(-1); menu.close() }
            }
            Text {
                visible: !menu.player || menu.player.subtitleTracks.length === 0
                width: parent.width; height: visible ? 24 : 0
                text: "No captions in this video"
                color: theme.muted
                font.pixelSize: 13
            }
            Repeater {
                model: menu.player ? menu.player.subtitleTracks.length : 0
                StoneButton {
                    required property int index
                    width: parent.width; height: 40
                    label: menu.trackLabel(index)
                    selected: menu.player && menu.player.activeSubtitleTrack === index
                    onActivated: { menu.trackRequested(index); menu.close() }
                }
            }
        }
    }
}
