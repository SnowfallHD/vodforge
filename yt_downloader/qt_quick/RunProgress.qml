import QtQuick

Item {
    id: progressTrack
    property string kind: ""
    property string status: ""
    property real progress: 0
    property var colors: theme
    implicitHeight: 5

    RunStatusTone { id: tone }

    Rectangle {
        anchors.fill: parent
        color: progressTrack.colors.surface_2
    }
    Rectangle {
        objectName: "runProgressFill"
        height: parent.height
        width: parent.width * tone.progressValue(progressTrack.kind, progressTrack.progress) / 100
        color: tone.colorFor(progressTrack.kind, progressTrack.status, progressTrack.colors)
        visible: width > 0
    }
}
