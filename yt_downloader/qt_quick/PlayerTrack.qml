import QtQuick

Item {
    id: track
    property string presentationRole: "control"
    property real position: 0
    Rectangle {
        x: 5
        y: track.height / 2 - 1.5
        width: Math.max(1, track.width - 10)
        height: 3
        radius: 1.5
        color: theme.border
        Rectangle {
            width: parent.width * Math.max(0, Math.min(1, track.position))
            height: parent.height
            radius: parent.radius
            color: theme.accent
        }
    }
}
