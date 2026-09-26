import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import QtMultimedia

Item {
    id: scene
    property var appBridge
    property var player
    property real volume: 0.8
    property alias videoSurface: videoSurface
    property string presentationMode: "embedded"
    property bool videoFill: false
    property bool restoreFillAfterCaptions: false
    property int requestedCaptionTrack: -2
    readonly property var activeVideoSurface: presentationMode === "embedded" ? videoSurface : presentationVideo
    readonly property string activeSurfaceName: activeVideoSurface.objectName
    readonly property var projection: appBridge.playerScene
    readonly property bool wide: width >= 1080
    readonly property real videoAspect: 16 / 9
    readonly property real stageMaxHeight: 450
    signal closeRequested()
    signal volumeRequested(real value)
    signal editDetailsRequested(string owner)

    function setPresentation(mode) {
        if (["embedded", "fullscreen", "floating"].indexOf(mode) < 0 ||
                (mode !== "embedded" && projection.kind !== "video"))
            return
        if (mode === presentationMode) return
        presentationMode = mode
        appBridge.recordPresentation(mode === "embedded" ? "returned" : mode)
    }
    function captionTrackChanged() {
        if (!player) return
        const active = player.activeSubtitleTrack
        if (active >= 0 && videoFill) {
            videoFill = false
            restoreFillAfterCaptions = true
            appBridge.recordPresentation("caption_fit_applied")
        } else if (active < 0 && requestedCaptionTrack === -1 && restoreFillAfterCaptions) {
            videoFill = true
            restoreFillAfterCaptions = false
            appBridge.recordPresentation("caption_fill_restored")
        }
        if (active === requestedCaptionTrack) requestedCaptionTrack = -2
    }
    function selectCaption(index) {
        if (!player || index < -1 || index >= player.subtitleTracks.length) return
        requestedCaptionTrack = index
        if (index >= 0 && videoFill) {
            videoFill = false
            restoreFillAfterCaptions = true
            appBridge.recordPresentation("caption_fit_applied")
        }
        player.activeSubtitleTrack = index
        captionTrackChanged()
        if (player.activeSubtitleTrack === index)
            appBridge.recordPresentation("captions_selected")
    }
    function toggleFill() {
        if (!videoFill && player && player.activeSubtitleTrack >= 0) {
            appBridge.recordPresentation("caption_fill_unavailable")
            return
        }
        videoFill = !videoFill
        if (!videoFill) restoreFillAfterCaptions = false
        appBridge.recordPresentation(videoFill ? "fill" : "fit")
    }
    function togglePlayback() {
        if (!player) return
        if (player.playbackState === MediaPlayer.PlayingState) player.pause()
        else player.play()
    }
    function seekTo(seconds) {
        if (player) appBridge.manualPlaybackSeek(Math.max(0, Math.min(seconds, player.duration / 1000)))
    }
    function showOptions() { playerOptions.open() }
    onPlayerChanged: {
        requestedCaptionTrack = -2
        restoreFillAfterCaptions = false
    }
    onPresentationModeChanged: {
        if (presentationMode === "embedded") presentationWindow.hide()
        else if (presentationMode === "fullscreen") presentationWindow.showFullScreen()
        else presentationWindow.showNormal()
    }
    onProjectionChanged: {
        if (projection.kind !== "video" && presentationMode !== "embedded")
            presentationMode = "embedded"
    }

    Window {
        id: presentationWindow
        objectName: "watchPresentationWindow"
        visible: false
        width: 780
        height: 480
        color: "black"
        title: scene.projection.title || "VODForge Player"
        flags: scene.presentationMode === "floating" ? Qt.Window | Qt.WindowStaysOnTopHint : Qt.Window
        onClosing: scene.setPresentation("embedded")
        VideoOutput {
            id: presentationVideo
            objectName: "watchPresentationVideoSurface"
            anchors.fill: parent
            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
        }
        HoverHandler { onPointChanged: presentationOverlay.reveal() }
        Text {
            objectName: "presentationCaptionText"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 68
            width: parent.width - 36
            text: presentationVideo.videoSink ? presentationVideo.videoSink.subtitleText : ""
            visible: text.length > 0 && scene.player && scene.player.activeSubtitleTrack >= 0
            color: "white"
            style: Text.Outline
            styleColor: "#09090d"
            font.pixelSize: 18
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
        }
        PlayerOverlay {
            id: presentationOverlay
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            controlPrefix: "presentation"
            player: scene.player
            volume: scene.volume
            previews: scene.appBridge.playbackPreviews
            heatmap: scene.appBridge.playbackHeatmap
            fullscreen: scene.presentationMode === "fullscreen"
            floating: scene.presentationMode === "floating"
            onPlayPauseRequested: scene.togglePlayback()
            onSeekRequested: function(seconds) { scene.seekTo(seconds) }
            onVolumeRequested: function(value) { scene.volumeRequested(value) }
            onFullscreenRequested: scene.setPresentation(scene.presentationMode === "fullscreen" ? "embedded" : "fullscreen")
            onFloatingRequested: scene.setPresentation(scene.presentationMode === "floating" ? "embedded" : "floating")
            onOptionsRequested: scene.showOptions()
            onCaptionsRequested: presentationCaptionMenu.open()
            onPreviewRequested: function(seconds) { scene.appBridge.hoverPlaybackPreview(seconds) }
        }
        CaptionTracks {
            id: presentationCaptionMenu
            objectName: "presentationCaptionsMenu"
            parent: presentationWindow.contentItem
            player: scene.player
            onTrackRequested: function(index) { scene.selectCaption(index) }
        }
    }

    ScrollView {
        id: viewport
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Column {
            width: viewport.availableWidth
            spacing: 16

            RowLayout {
                width: parent.width
                height: 65
                spacing: 16
                StoneButton {
                    label: "Back to Watch"
                    size: "inline"
                    Layout.preferredWidth: 145
                    onActivated: scene.closeRequested()
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 3
                    Text {
                        text: scene.projection.title || "Saved media"
                        color: theme.text
                        font.pixelSize: 25
                        font.bold: true
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                    }
                    Text {
                        text: (scene.projection.creator || "") + (scene.projection.category ? " · " + scene.projection.category : "")
                        color: theme.muted
                        font.pixelSize: 14
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                    }
                }
                StoneButton {
                    label: "View in Library"
                    size: "inline"
                    Layout.preferredWidth: 150
                    onActivated: scene.appBridge.openWatchDetails(scene.projection.owner)
                }
            }

            RowLayout {
                width: scene.wide ? Math.min(parent.width, scene.stageMaxHeight * scene.videoAspect + 334) : parent.width
                x: (parent.width - width) / 2
                spacing: 24
                Column {
                    id: stageColumn
                    objectName: "playerStageColumn"
                    Layout.fillWidth: true
                    Layout.preferredWidth: scene.wide ? scene.stageMaxHeight * scene.videoAspect : scene.width
                    spacing: 10

                    Item {
                        id: mediaStage
                        objectName: "playerMediaStage"
                        height: Math.max(180, Math.min(scene.stageMaxHeight, parent.width / scene.videoAspect, scene.height - 205))
                        width: Math.min(parent.width, height * scene.videoAspect)
                        x: (parent.width - width) / 2
                        clip: true
                        layer.enabled: true
                        layer.effect: MultiEffect {
                            maskEnabled: true
                            maskSource: ShaderEffectSource {
                                sourceItem: Rectangle {
                                    width: mediaStage.width
                                    height: mediaStage.height
                                    radius: 11
                                    color: "white"
                                }
                            }
                        }
                        Rectangle { anchors.fill: parent; color: "#09090d" }
                        VideoOutput {
                            id: videoSurface
                            objectName: "watchVideoSurface"
                            anchors.fill: parent
                            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
                        }
                        HoverHandler { onPointChanged: embeddedOverlay.reveal() }
                        TapHandler { onTapped: scene.togglePlayback() }
                        Text {
                            objectName: "embeddedCaptionText"
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 110
                            width: parent.width - 28
                            text: videoSurface.videoSink ? videoSurface.videoSink.subtitleText : ""
                            visible: text.length > 0 && scene.player && scene.player.activeSubtitleTrack >= 0
                            color: "white"
                            style: Text.Outline
                            styleColor: "#09090d"
                            font.pixelSize: 18
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }
                        PlayerOverlay {
                            id: embeddedOverlay
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            player: scene.player
                            volume: scene.volume
                            previews: scene.appBridge.playbackPreviews
                            heatmap: scene.appBridge.playbackHeatmap
                            onPlayPauseRequested: scene.togglePlayback()
                            onSeekRequested: function(seconds) { scene.seekTo(seconds) }
                            onVolumeRequested: function(value) { scene.volumeRequested(value) }
                            onFullscreenRequested: scene.setPresentation("fullscreen")
                            onFloatingRequested: scene.setPresentation("floating")
                            onOptionsRequested: scene.showOptions()
                            onCaptionsRequested: captionsMenu.open()
                            onPreviewRequested: function(seconds) { scene.appBridge.hoverPlaybackPreview(seconds) }
                        }
                    }
                    Text {
                        width: parent.width
                        text: "This saved media could not be played. Check that the file is still available, then try again."
                        color: theme.muted
                        font.pixelSize: 14
                        visible: scene.player && scene.player.error !== MediaPlayer.NoError
                        wrapMode: Text.WordWrap
                    }
                }

                Column {
                    objectName: "playerRelatedSide"
                    visible: scene.wide && (scene.projection.upNext || []).length > 0
                    Layout.preferredWidth: visible ? 310 : 0
                    Layout.alignment: Qt.AlignTop
                    spacing: 9
                    Text {
                        text: scene.projection.queued ? "UP NEXT" : "MORE TO WATCH"
                        color: theme.muted
                        font.pixelSize: 12
                        font.bold: true
                    }
                    Repeater {
                        model: (scene.projection.upNext || []).slice(0, 4)
                        StoneField {
                            required property var modelData
                            width: 310
                            height: 83
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 8
                                ArtworkImage {
                                    source: modelData.artwork || ""
                                    Layout.preferredWidth: 92
                                    Layout.preferredHeight: 58
                                    inset: 0
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Text { text: modelData.title; color: theme.text; font.pixelSize: 13; font.bold: true; elide: Text.ElideRight; Layout.fillWidth: true }
                                    Text { text: modelData.creator; color: theme.muted; font.pixelSize: 12; elide: Text.ElideRight; Layout.fillWidth: true }
                                    RowLayout {
                                        spacing: 4
                                        StoneButton {
                                            label: "Play"
                                            size: "inline"
                                            Layout.preferredWidth: 65
                                            onActivated: scene.appBridge.playPlayerRelated(modelData.owner)
                                        }
                                        StoneButton {
                                            label: "Details"
                                            size: "inline"
                                            Layout.preferredWidth: 75
                                            onActivated: scene.appBridge.detailsPlayerRelated(modelData.owner)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Column {
                objectName: "playerRelatedCompact"
                visible: !scene.wide && (scene.projection.upNext || []).length > 0
                width: parent.width
                spacing: 8
                Text { text: scene.projection.queued ? "UP NEXT" : "MORE TO WATCH"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Row {
                    spacing: 10
                    Repeater {
                        model: (scene.projection.upNext || []).slice(0, 3)
                        StoneButton {
                            required property var modelData
                            label: modelData.title
                            width: Math.min(220, (scene.width - 20) / 3)
                            height: 40
                            size: "inline"
                            onActivated: scene.appBridge.playPlayerRelated(modelData.owner)
                        }
                    }
                }
            }

            Column {
                objectName: "watchChapters"
                visible: scene.appBridge.playbackChapters.length > 0
                width: parent.width
                spacing: 6
                Text { text: "CHAPTERS"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Repeater {
                    model: scene.appBridge.playbackChapters
                    StoneButton {
                        required property var modelData
                        required property int index
                        width: Math.min(460, scene.width)
                        height: 34
                        label: Math.floor(modelData.start_time / 60) + ":" +
                            ("0" + Math.floor(modelData.start_time % 60)).slice(-2) +
                            "  " + (modelData.title || "Untitled chapter")
                        transientMaterial: false
                        onActivated: scene.appBridge.seekPlaybackChapter(index)
                    }
                }
            }

            Column {
                objectName: "playerRecentRail"
                visible: (scene.projection.recent || []).length > 1
                width: parent.width
                spacing: 8
                Text { text: "RECENTLY ADDED"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                ScrollView {
                    width: parent.width
                    height: 164
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                    ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                    Row {
                        spacing: 12
                        Repeater {
                            model: (scene.projection.recent || []).slice(0, 8)
                            StoneButton {
                                required property var modelData
                                width: 207; height: 142
                                label: ""
                                accessibilityLabel: "Play " + modelData.title
                                transientMaterial: false
                                onActivated: scene.appBridge.playPlayerRelated(modelData.owner)
                                ArtworkImage {
                                    x: 7; y: 7
                                    width: parent.width - 14; height: 105
                                    source: modelData.artwork || ""
                                    inset: 0
                                }
                                Text {
                                    x: 9; y: 117
                                    width: parent.width - 18
                                    text: modelData.title
                                    color: theme.text
                                    font.pixelSize: 13
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 8
                Text { text: "ABOUT THIS MEDIA"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Text {
                    text: scene.projection.description || "No description saved for this media."
                    color: theme.text
                    width: parent.width
                    font.pixelSize: 14
                    wrapMode: Text.WordWrap
                }
            }
            Column {
                width: parent.width
                spacing: 8
                Text { text: "YOUR DETAILS"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Text {
                    text: (scene.projection.category ? "Collection: " + scene.projection.category + "\n" : "") +
                          ((scene.projection.tags || []).length ? "Tags: " + scene.projection.tags.join(", ") + "\n" : "") +
                          (scene.projection.note ? "Your note: " + scene.projection.note : "") ||
                          "Add a note or tags in Library."
                    color: theme.muted
                    width: parent.width
                    font.pixelSize: 14
                    wrapMode: Text.WordWrap
                }
                StoneButton {
                    label: "Edit your details"
                    width: 165
                    height: 40
                    onActivated: scene.editDetailsRequested(scene.projection.owner)
                }
            }
            Repeater {
                model: [
                    { title: "SOURCE DETAILS", facts: scene.projection.source || [] },
                    { title: "OUTPUT DETAILS", facts: scene.projection.output || [] }
                ]
                Column {
                    required property var modelData
                    width: scene.width
                    spacing: 8
                    Text { text: modelData.title; color: theme.muted; font.pixelSize: 12; font.bold: true }
                    Repeater {
                        model: modelData.facts
                        RowLayout {
                            required property var modelData
                            width: scene.width
                            Text { text: modelData.label; color: theme.muted; font.pixelSize: 14; Layout.preferredWidth: 160 }
                            Text { text: modelData.value; color: theme.text; font.pixelSize: 14; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                        }
                    }
                }
            }
            Item { width: 1; height: 14 }
        }
    }
    CaptionTracks {
        id: captionsMenu
        objectName: "playerCaptionsMenu"
        player: scene.player
        onTrackRequested: function(index) { scene.selectCaption(index) }
    }
    Popup {
        id: playerOptions
        objectName: "playerOptionsMenu"
        parent: scene.presentationMode === "embedded" ? scene : presentationWindow.contentItem
        x: Math.max(12, (parent.width - width) / 2)
        y: Math.max(12, parent.height - height - 104)
        width: 244
        height: 102
        padding: 5
        background: StoneField {}
        Column {
            width: parent.width
            spacing: 2
            StoneButton {
                objectName: "playerFitButton"
                width: parent.width; height: 42
                label: "Fit entire video"
                selected: !scene.videoFill
                onActivated: { if (scene.videoFill) scene.toggleFill(); playerOptions.close() }
            }
            StoneButton {
                objectName: "playerFillButton"
                width: parent.width; height: 42
                label: "Fill frame (crop)"
                selected: scene.videoFill
                enabled: !scene.player || scene.player.activeSubtitleTrack < 0
                onActivated: { if (!scene.videoFill) scene.toggleFill(); playerOptions.close() }
            }
        }
    }
}
