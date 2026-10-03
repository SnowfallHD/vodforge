import QtQuick
import QtMultimedia

Item {
    id: preview
    objectName: "recordedFeaturePreview"
    property url recordingSource: ""
    property url posterSource: ""
    property string description: "Recorded UI demonstration"
    property bool active: false
    property bool reducedMotion: false
    property bool pausedByUser: false
    readonly property bool windowVisible: Window.window &&
        Window.window.visibility !== Window.Hidden && Window.window.visibility !== Window.Minimized
    property bool foreground: Window.window && Window.window.active
    readonly property bool loadRecording: active && visible && windowVisible && !reducedMotion && recordingSource.toString().length > 0
    readonly property bool playRecording: loadRecording && foreground && !pausedByUser
    readonly property bool frameReady: recordingLoader.item && recordingLoader.item.frameReady
    Accessible.role: Accessible.Graphic
    Accessible.name: description
    onRecordingSourceChanged: pausedByUser = false

    Image {
        objectName: "recordedPreviewPoster"
        anchors.fill: parent
        source: preview.posterSource
        fillMode: Image.PreserveAspectFit
        visible: !preview.frameReady
        smooth: true
    }
    Loader {
        id: recordingLoader
        objectName: "recordedPreviewLoader"
        anchors.fill: parent
        active: preview.loadRecording
        sourceComponent: Item {
            readonly property bool frameReady: video.sourceRect.width > 0
            function syncPlayback() {
                if (preview.playRecording) player.play()
                else player.pause()
            }
            Connections {
                target: preview
                function onPlayRecordingChanged() { recordingLoader.item.syncPlayback() }
            }
            Component.onDestruction: player.stop()
            VideoOutput {
                id: video
                objectName: "recordedPreviewVideo"
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
                endOfStreamPolicy: VideoOutput.KeepLastFrame
            }
            MediaPlayer {
                id: player
                objectName: "recordedPreviewPlayer"
                source: preview.recordingSource
                loops: MediaPlayer.Infinite
                videoOutput: video
                audioOutput: AudioOutput { muted: true; volume: 0 }
                onSourceChanged: video.clearOutput()
                onMediaStatusChanged: {
                    if (recordingLoader.item && (mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia))
                        recordingLoader.item.syncPlayback()
                }
            }
        }
    }
    StoneButton {
        objectName: "recordedPreviewPause"
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 6
        visible: preview.loadRecording
        label: preview.pausedByUser ? "Play" : "Pause"
        accessibilityLabel: label + " recorded preview"
        size: "inline"
        onActivated: preview.pausedByUser = !preview.pausedByUser
    }
}
