import QtQuick
import QtQuick.Controls

AnchoredPopup {
    id: menu
    property var tracks: []
    property int selectedIndex: -1
    signal trackRequested(int index)
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
                label: "Off"
                selected: menu.selectedIndex < 0
                onActivated: { menu.trackRequested(-1); menu.close() }
            }
            Text {
                visible: menu.tracks.length === 0
                width: parent.width; height: visible ? 24 : 0
                text: "No translated subtitles saved"
                color: theme.muted
                font.pixelSize: 13
            }
            Repeater {
                model: menu.tracks
                StoneButton {
                    required property var modelData
                    width: parent.width; height: 40
                    label: modelData.label
                    selected: menu.selectedIndex === modelData.index
                    onActivated: { menu.trackRequested(modelData.index); menu.close() }
                }
            }
        }
    }
}
