import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import QtMultimedia

Item {
    id: controls
    required property var player
    required property real volume
    property var previews: []
    property var chapters: []
    property url fallbackArtwork: ""
    property url lastPreviewImage: ""
    property real hoverSeconds: 0
    property string controlPrefix: "player"
    property bool fullscreen: false
    property bool floating: false
    property bool compact: width < 660
    readonly property bool controlsShown: visible
    signal playPauseRequested()
    signal seekRequested(real seconds)
    signal volumeRequested(real value)
    signal fullscreenRequested()
    signal floatingRequested()
    signal optionsRequested(var anchor)
    property bool originalCaptionsAvailable: false
    property bool originalCaptionsEnabled: false
    property bool translatedSubtitlesAvailable: false
    property bool translatedSubtitlesEnabled: false
    property string captionStatus: ""
    signal captionsRequested()
    signal subtitlesRequested(var anchor)
    signal previewRequested(real seconds)

    property bool presentationAvailable: true
    property bool surfaceHovered: false
    property bool menuOpen: false
    readonly property bool keyboardEngaged: focusInside(Window.window ? Window.window.activeFocusItem : null)
    readonly property bool interactionHeld: seek.pressed || volumeSlider.pressed || menuOpen || keyboardEngaged
    readonly property real minimumControlsWidth: playControl.width + backControl.width + forwardControl.width
        + muteControl.width + 5 * 3 + 50 + compactTimeMetrics.advanceWidth
        + captionsControl.width + subtitlesControl.width + optionsControl.width + floatingControl.width + fullscreenControl.width
        + 4 * 3 + 48
    TextMetrics {
        id: compactTimeMetrics
        font: timeLabel.font
        text: {
            const position = Math.floor((controls.player ? controls.player.position : 0) / 1000)
            return Math.floor(position / 60) + ":" + ("0" + position % 60).slice(-2)
        }
    }
    function focusInside(item) {
        while (item) {
            if (item === controls) return true
            item = item.parent
        }
        return false
    }
    function reveal() { surfaceHovered = true }
    objectName: controlPrefix === "player" ? "embeddedPlayerOverlay" : "presentationPlayerOverlay"
    height: 104
    visible: presentationAvailable && (surfaceHovered || interactionHeld)
    onPlayerChanged: { lastPreviewImage = "" }
    onPreviewsChanged: {
        if (previews.length && previews[0].image)
            lastPreviewImage = previews[0].image
    }

    // The single lower scrim belongs to the video overlay, as in the native player.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#00000000" }
            GradientStop { position: 1; color: "#dd000000" }
        }
    }
    Text {
        objectName: "playerCurrentChapterTitle"
        x: 18; y: 0
        width: parent.width - 36
        text: chapterTrack.currentChapter
        color: "white"
        font.pixelSize: 11
        elide: Text.ElideRight
        HoverHandler { id: chapterTitleHover }
        ToolTip {
            objectName: "playerChapterTitleTooltip"
            visible: chapterTitleHover.hovered && !!chapterTrack.currentChapter
            text: chapterTrack.currentChapter
            width: Math.min(360, controls.width - 24)
            background: Rectangle { color: theme.surface_2; radius: 8; border.color: theme.border }
            contentItem: Text {
                text: chapterTrack.currentChapter
                color: theme.text
                wrapMode: Text.WrapAnywhere
                font.pixelSize: 12
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
        background: ChapterSeekTrack {
            id: chapterTrack
            objectName: "playerChapterTrack"
            position: seek.visualPosition
            duration: seek.to / 1000
            chapters: controls.player && controls.player.duration > 0 ? controls.chapters : []
        }
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
            controls.previewRequested(controls.hoverSeconds)
        }
        onEntered: track(mouseX)
        onPositionChanged: function(mouse) { track(mouse.x) }
        onExited: {}
    }
    Rectangle {
        id: hoverPreview
        HoverHandler { id: previewHover }
        objectName: "playerSeekPreview"
        visible: (seekHover.containsMouse || previewHover.hovered) && controls.player && controls.player.duration > 0
        width: 160; height: chapterTrack.chapterAt(controls.hoverSeconds) ? 132 : 112; radius: 7
        x: Math.max(4, Math.min(controls.width - width - 4, seekHover.x + seekHover.mouseX - width / 2))
        y: -height + 9
        color: "#f009090d"
        border.width: 1
        border.color: theme.accent
        Image {
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.margins: 4
            height: 85
            source: controls.lastPreviewImage || controls.fallbackArtwork
            fillMode: Image.PreserveAspectFit
            smooth: true
        }
        Text {
            objectName: "playerHoverChapterTitle"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.margins: 6
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 25
            text: chapterTrack.chapterAt(controls.hoverSeconds)
            visible: !!text
            color: "white"
            font.pixelSize: 11
            elide: Text.ElideRight
            horizontalAlignment: Text.AlignHCenter
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
        objectName: "playerOverlayLeftActions"
        anchors.left: parent.left
        anchors.leftMargin: 18
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        spacing: compact ? 3 : 8
        StoneButton {
            id: playControl
            objectName: "playerOverlayPlay"
            width: 38; height: 36
            label: ""
            sceneIcon: controls.player && controls.player.playbackState === MediaPlayer.PlayingState ? "pause" : "play"
            accessibilityLabel: sceneIcon === "pause" ? "Pause" : "Play"
            transientMaterial: false
            onActivated: controls.playPauseRequested()
        }
        StoneButton {
            id: backControl
            objectName: "playerOverlayBack10"
            width: 38; height: 36; label: ""
            sceneIcon: "backward"; accessibilityLabel: "Jump back 10 seconds"
            transientMaterial: false
            onActivated: controls.seekRequested(Math.max(0, (controls.player ? controls.player.position : 0) / 1000 - 10))
        }
        StoneButton {
            id: forwardControl
            objectName: "playerOverlayForward10"
            width: 38; height: 36; label: ""
            sceneIcon: "forward"; accessibilityLabel: "Jump forward 10 seconds"
            transientMaterial: false
            onActivated: controls.seekRequested(((controls.player ? controls.player.position : 0) / 1000) + 10)
        }
        StoneButton {
            id: muteControl
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
            id: timeLabel
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
        objectName: "playerOverlayRightActions"
        anchors.right: parent.right
        anchors.rightMargin: 18
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 14
        spacing: compact ? 3 : 8
        StoneButton {
            id: captionsControl
            objectName: controls.controlPrefix === "player" ? "playerCaptionsButton" : "presentationCaptionsButton"
            width: 38; height: 36; label: ""; sceneIcon: "captions"
            accessibilityLabel: controls.originalCaptionsAvailable ? "Captions: " + (controls.originalCaptionsEnabled ? "On" : "Off") : "Captions unavailable: " + controls.captionStatus
            transientMaterial: false
            enabled: controls.originalCaptionsAvailable
            selected: controls.originalCaptionsEnabled
            ToolTip.visible: hovered
            ToolTip.text: controls.originalCaptionsAvailable ? "Original-language captions: " + (controls.originalCaptionsEnabled ? "On" : "Off") : (controls.captionStatus || "No identified original captions saved")
            onActivated: controls.captionsRequested()
        }
        StoneButton {
            id: subtitlesControl
            objectName: controls.controlPrefix === "player" ? "playerSubtitlesButton" : "presentationSubtitlesButton"
            // Keep the short label readable instead of eliding it into baseline dots.
            width: 46; height: 36; label: "Sub"; sceneIcon: ""
            accessibilityLabel: controls.translatedSubtitlesAvailable ? "Translated subtitles: " + (controls.translatedSubtitlesEnabled ? "On" : "Off") : "Translated subtitles unavailable: none saved"
            transientMaterial: false
            enabled: controls.translatedSubtitlesAvailable
            selected: controls.translatedSubtitlesEnabled
            ToolTip.visible: hovered
            ToolTip.text: controls.translatedSubtitlesAvailable ? "Translated subtitles" : "No translated subtitles saved in this video"
            onActivated: controls.subtitlesRequested(this)
        }
        StoneButton {
            id: optionsControl
            objectName: "playerOverlayOptions"
            width: 38; height: 36; label: ""; sceneIcon: "settings"
            accessibilityLabel: "Playback options"; transientMaterial: false
            onActivated: controls.optionsRequested(this)
        }
        StoneButton {
            id: floatingControl
            objectName: "playerOverlayFloating"
            width: 38; height: 36; label: ""; sceneIcon: "floating"
            accessibilityLabel: controls.floating ? "Return to main window" : "Watch in floating window"
            transientMaterial: false
            onActivated: controls.floatingRequested()
        }
        StoneButton {
            id: fullscreenControl
            objectName: "playerOverlayFullscreen"
            width: 38; height: 36; label: ""; sceneIcon: "fullscreen"
            accessibilityLabel: controls.fullscreen ? "Exit full screen" : "Full screen"
            transientMaterial: false
            onActivated: controls.fullscreenRequested()
        }
    }
}
