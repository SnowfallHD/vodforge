import QtQuick
import QtQuick.Controls

Popup {
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
    x: Math.max(0, (parent.width - width) / 2)
    y: Math.max(0, (parent.height - height) / 2)
    width: Math.min(245, parent.width - 24)
    height: Math.min(250, 52 + (player ? player.subtitleTracks.length + 1 : 1) * 42)
    padding: 5
    background: StoneField {}
    ScrollView {
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        Column {
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
