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
    readonly property bool frameReady: recordingLoader.item &&
        recordingLoader.item.sourceOwner.toString() === recordingSource.toString() && recordingLoader.item.frameReady
    readonly property var mediaPlayer: recordingLoader.item ? recordingLoader.item.mediaPlayer : null
    Accessible.role: Accessible.Graphic
    Accessible.name: description
    // Each slide owns a separate decoder/output. Queued frames from a retired
    // source must never be adopted by a newly selected slide.
    onRecordingSourceChanged: {
        pausedByUser = false
        recordingLoader.sourceComponent = null
        recordingLoader.sourceComponent = recordingComponent
    }

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
        sourceComponent: recordingComponent
        onLoaded: item.sourceOwner = preview.recordingSource
    }
    Component {
        id: recordingComponent
        Item {
            id: recording
            property url sourceOwner: ""
            property alias mediaPlayer: player
            readonly property bool frameReady: video.sourceRect.width > 0
            function syncPlayback() {
                if (preview.playRecording) player.play()
                else player.pause()
            }
            Connections {
                target: preview
                function onPlayRecordingChanged() { recording.syncPlayback() }
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
                source: recording.sourceOwner
                loops: MediaPlayer.Infinite
                videoOutput: video
                audioOutput: AudioOutput { muted: true; volume: 0 }
                onSourceChanged: video.clearOutput()
                onMediaStatusChanged: {
                    if (recordingLoader.item && (mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia))
                        recording.syncPlayback()
                }
            }
        }
    }
}
