import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtMultimedia

Item {
    id: controls
    required property var player
    required property real volume
    property var previews: []
    property var heatmap: []
    property real hoverSeconds: 0
    property string controlPrefix: "player"
    property bool fullscreen: false
    property bool floating: false
    property bool compact: width < 660
    property bool controlsShown: true
    signal playPauseRequested()
    signal seekRequested(real seconds)
    signal volumeRequested(real value)
    signal fullscreenRequested()
    signal floatingRequested()
    signal optionsRequested()
    signal captionsRequested()
    signal previewRequested(real seconds)

    function reveal() {
        controlsShown = true
        if (player && player.playbackState === MediaPlayer.PlayingState)
            hideTimer.restart()
    }

    objectName: controlPrefix === "player" ? "embeddedPlayerOverlay" : "presentationPlayerOverlay"
    height: 104
    visible: controlsShown
    onPlayerChanged: controlsShown = true
    HoverHandler {
        onHoveredChanged: {
            if (hovered) {
                controls.reveal()
                hideTimer.stop()
            } else if (controls.player && controls.player.playbackState === MediaPlayer.PlayingState)
                hideTimer.restart()
        }
    }
    Timer {
        id: hideTimer
        interval: 3000
        onTriggered: {
            if (controls.player && controls.player.playbackState === MediaPlayer.PlayingState)
                controls.controlsShown = false
        }
    }
    Connections {
        target: controls.player
        function onPlaybackStateChanged() {
            controls.controlsShown = true
            if (controls.player.playbackState === MediaPlayer.PlayingState)
                hideTimer.restart()
            else hideTimer.stop()
        }
    }

    // The single lower scrim belongs to the video overlay, as in the native player.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#00000000" }
            GradientStop { position: 1; color: "#dd000000" }
        }
    }
    Item {
        id: heatmapTrack
        objectName: "watchHeatmap"
        visible: controls.heatmap.length > 0 && controls.player && controls.player.duration > 0
        x: 23; y: 1
        width: controls.width - 46
        height: 14
        clip: true
        Repeater {
            model: controls.heatmap
            Rectangle {
                required property var modelData
                x: Math.max(0, Math.min(heatmapTrack.width,
                    modelData.start_time * heatmapTrack.width * 1000 /
                    Math.max(1, controls.player ? controls.player.duration : 0)))
                width: Math.max(1, (modelData.end_time - modelData.start_time) *
                    heatmapTrack.width * 1000 /
                    Math.max(1, controls.player ? controls.player.duration : 0))
                height: Math.max(2, 13 * modelData.value)
                y: heatmapTrack.height - height
                color: theme.accent
                opacity: 0.72
            }
        }
    }
    Basic.Slider {
        id: seek
        objectName: "playerOverlaySeek"
        Accessible.name: "Playback position"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 18
        anchors.rightMargin: 18
        y: 18
        height: 22
        from: 0
        to: Math.max(1, controls.player ? controls.player.duration : 0)
        value: controls.player ? controls.player.position : 0
        onMoved: controls.seekRequested(value / 1000)
        background: PlayerTrack { position: seek.visualPosition }
        handle: Rectangle {
            x: 5 + seek.visualPosition * (seek.width - 20)
            y: seek.height / 2 - 5
            width: 10; height: 10; radius: 5
            color: theme.text
        }
    }
    MouseArea {
        id: seekHover
        objectName: "playerSeekHover"
        x: 18; y: 12
        width: parent.width - 36
        height: 34
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        function track(xPosition) {
            controls.hoverSeconds = Math.max(0, Math.min(1, xPosition / Math.max(1, width))) *
                                    ((controls.player ? controls.player.duration : 0) / 1000)
            hoverDebounce.restart()
        }
        onEntered: track(mouseX)
        onPositionChanged: function(mouse) { track(mouse.x) }
        onExited: hoverDebounce.stop()
    }
    Timer {
        id: hoverDebounce
        interval: 120
        onTriggered: controls.previewRequested(controls.hoverSeconds)
    }
    Rectangle {
        id: hoverPreview
        objectName: "playerSeekPreview"
        visible: seekHover.containsMouse && controls.player && controls.player.duration > 0
        width: 160; height: 112; radius: 7
        x: Math.max(4, Math.min(controls.width - width - 4, seekHover.x + seekHover.mouseX - width / 2))
        y: -height + 9
        color: "#f009090d"
        border.width: 1
        border.color: theme.accent
        Image {
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 4
            height: 85
            source: controls.previews.length &&
                    Math.abs(controls.previews[0].position - controls.hoverSeconds) < 1.5
                    ? controls.previews[0].image : ""
            fillMode: Image.PreserveAspectFit
            smooth: true
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 5
            text: Math.floor(controls.hoverSeconds / 60) + ":" +
                  ("0" + Math.floor(controls.hoverSeconds % 60)).slice(-2)
            color: "white"
            font.pixelSize: 13
        }
    }
    Row {
        id: leftActions
        anchors.left: parent.left
        anchors.leftMargin: 18
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        spacing: compact ? 3 : 8
        StoneButton {
            objectName: "playerOverlayPlay"
            width: 38; height: 36
            label: ""
            sceneIcon: controls.player && controls.player.playbackState === MediaPlayer.PlayingState ? "pause" : "play"
            accessibilityLabel: sceneIcon === "pause" ? "Pause" : "Play"
            transientMaterial: false
            onActivated: controls.playPauseRequested()
        }
        StoneButton {
            objectName: "playerOverlayBack10"
            width: 38; height: 36; label: ""
            sceneIcon: "backward"; accessibilityLabel: "Jump back 10 seconds"
            transientMaterial: false
            onActivated: controls.seekRequested(Math.max(0, (controls.player ? controls.player.position : 0) / 1000 - 10))
        }
        StoneButton {
            objectName: "playerOverlayForward10"
            width: 38; height: 36; label: ""
            sceneIcon: "forward"; accessibilityLabel: "Jump forward 10 seconds"
            transientMaterial: false
            onActivated: controls.seekRequested(((controls.player ? controls.player.position : 0) / 1000) + 10)
        }
        StoneButton {
            objectName: "playerOverlayMute"
            width: 38; height: 36; label: ""
            sceneIcon: controls.volume <= 0 ? "muted" : "volume"
            accessibilityLabel: controls.volume <= 0 ? "Unmute" : "Mute"
            transientMaterial: false
            property real previousVolume: 0.8
            onActivated: {
                if (controls.volume > 0) { previousVolume = controls.volume; controls.volumeRequested(0) }
                else controls.volumeRequested(previousVolume)
            }
        }
        Basic.Slider {
            id: volumeSlider
            objectName: "playerOverlayVolume"
            Accessible.name: "Volume"
            width: controls.compact ? 50 : 86
            height: 36
            from: 0; to: 1; value: controls.volume
            onMoved: controls.volumeRequested(value)
            background: PlayerTrack { position: volumeSlider.visualPosition }
            handle: Rectangle {
                x: 5 + volumeSlider.visualPosition * (volumeSlider.width - 20)
                y: volumeSlider.height / 2 - 5
                width: 10; height: 10; radius: 5; color: theme.text
            }
        }
        Text {
            objectName: "playerOverlayTime"
            anchors.verticalCenter: parent.verticalCenter
            text: {
                const position = Math.floor((controls.player ? controls.player.position : 0) / 1000)
                const duration = Math.floor((controls.player ? controls.player.duration : 0) / 1000)
                function clock(value) { return Math.floor(value / 60) + ":" + ("0" + value % 60).slice(-2) }
                return clock(position) + (controls.compact ? "" : " / " + clock(duration))
            }
            color: "white"
            font.pixelSize: 13
        }
    }
    Row {
        id: rightActions
        anchors.right: parent.right
        anchors.rightMargin: 18
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        spacing: compact ? 3 : 8
        StoneButton {
            objectName: controls.controlPrefix === "player" ? "playerCaptionsButton" : "presentationCaptionsButton"
            width: 38; height: 36; label: ""; sceneIcon: "captions"
            accessibilityLabel: "Captions"; transientMaterial: false
            onActivated: controls.captionsRequested()
        }
        StoneButton {
            objectName: "playerOverlayOptions"
            width: 38; height: 36; label: ""; sceneIcon: "settings"
            accessibilityLabel: "Playback options"; transientMaterial: false
            onActivated: controls.optionsRequested()
        }
        StoneButton {
            objectName: "playerOverlayFloating"
            width: 38; height: 36; label: ""; sceneIcon: "floating"
            accessibilityLabel: controls.floating ? "Return to main window" : "Watch in floating window"
            transientMaterial: false
            onActivated: controls.floatingRequested()
        }
        StoneButton {
            objectName: "playerOverlayFullscreen"
            width: 38; height: 36; label: ""; sceneIcon: "fullscreen"
            accessibilityLabel: controls.fullscreen ? "Exit full screen" : "Full screen"
            transientMaterial: false
            onActivated: controls.fullscreenRequested()
        }
    }
}
