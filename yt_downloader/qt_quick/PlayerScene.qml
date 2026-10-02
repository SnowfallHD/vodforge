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
    // Sample Qt's displayed geometry after layout settles; directly binding
    // the stage ratio to contentRect creates a geometry dependency loop.
    property real displayedVideoAspect: 16 / 9
    readonly property real videoAspect: displayedVideoAspect
    function refreshDisplayedAspect() {
        const output = activeVideoSurface
        if (output.sourceRect.width <= 0 || output.sourceRect.height <= 0 ||
                output.contentRect.width <= 0 || output.contentRect.height <= 0) return
        const aspect = output.contentRect.width / output.contentRect.height
        if (isFinite(aspect) && aspect > 0 && Math.abs(displayedVideoAspect - aspect) > 0.0001)
            displayedVideoAspect = aspect
    }
    onActiveVideoSurfaceChanged: Qt.callLater(refreshDisplayedAspect)
    Connections {
        target: scene.activeVideoSurface
        function onContentRectChanged() { Qt.callLater(scene.refreshDisplayedAspect) }
        function onSourceRectChanged() { Qt.callLater(scene.refreshDisplayedAspect) }
    }
    readonly property real stageMaxHeight: Math.max(180, height - 145)
    readonly property real stageHeightLimit: stageMaxHeight
    function eligibleCards(rows) {
        const seen = {}
        return (rows || []).filter(function(row) {
            if (!row || !row.owner || row.owner === projection.owner || seen[row.owner]) return false
            seen[row.owner] = true
            return true
        })
    }
    readonly property var primaryRelated: eligibleCards(projection.upNext)
    readonly property var recentCards: eligibleCards(projection.recent)
    readonly property bool relatedFallback: primaryRelated.length === 0
    readonly property var relatedCards: relatedFallback ? recentCards : primaryRelated
    readonly property bool relatedLoading: projection.loading === true || !projection.owner
    readonly property bool hasRelatedSide: wide
    readonly property real relatedSideWidth: hasRelatedSide ? Math.min(360, Math.max(270, width * 0.22)) : 0
    signal closeRequested()
    signal volumeRequested(real value)
    signal editDetailsRequested(string owner)

    function clearVideoFrames() {
        videoSurface.clearOutput()
        presentationVideo.clearOutput()
    }
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
    function showOptions(anchor) { playerOptions.anchorItem = anchor; playerOptions.toggleFrom(anchor) }
    onPlayerChanged: {
        requestedCaptionTrack = -2
        restoreFillAfterCaptions = false
    }
    onPresentationModeChanged: {
        if (presentationMode === "embedded") {
            // Hiding a fullscreen Cocoa window leaves its native Space alive.
            // Retire fullscreen before moving the video back into the app.
            if (presentationWindow.visibility === Window.FullScreen)
                presentationWindow.showNormal()
            presentationWindow.hide()
        } else if (presentationMode === "fullscreen") presentationWindow.showFullScreen()
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
        minimumWidth: Math.ceil(presentationOverlay.minimumControlsWidth)
        minimumHeight: presentationOverlay.height
        color: "black"
        title: scene.projection.title || "VODForge Player"
        // Windows adds default decorations only for a bare Qt.Window. Adding
        // the on-top hint requires requesting the native controls explicitly.
        flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
               Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint |
               Qt.WindowCloseButtonHint |
               (scene.presentationMode === "floating" ? Qt.WindowStaysOnTopHint : 0)
        onClosing: scene.setPresentation("embedded")
        Shortcut {
            sequence: "Escape"
            enabled: presentationWindow.visible
            onActivated: scene.setPresentation("embedded")
        }
        VideoOutput {
            id: presentationVideo
            objectName: "watchPresentationVideoSurface"
            anchors.fill: parent
            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
            endOfStreamPolicy: VideoOutput.KeepLastFrame
            TapHandler { onTapped: scene.togglePlayback() }
        }
        HoverHandler { id: presentationHover }
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
            surfaceHovered: presentationHover.hovered
            menuOpen: playerOptions.visible || presentationCaptionMenu.visible
            chapters: scene.appBridge.playbackChapters
            player: scene.player
            volume: scene.volume
            previews: scene.appBridge.playbackPreviews
            fallbackArtwork: scene.projection.artwork || ""
            fullscreen: scene.presentationMode === "fullscreen"
            floating: scene.presentationMode === "floating"
            onPlayPauseRequested: scene.togglePlayback()
            onSeekRequested: function(seconds) { scene.seekTo(seconds) }
            onVolumeRequested: function(value) { scene.volumeRequested(value) }
            onFullscreenRequested: scene.setPresentation(scene.presentationMode === "fullscreen" ? "embedded" : "fullscreen")
            onFloatingRequested: scene.setPresentation(scene.presentationMode === "floating" ? "embedded" : "floating")
            onOptionsRequested: function(anchor) { scene.showOptions(anchor) }
            onCaptionsRequested: function(anchor) { presentationCaptionMenu.anchorItem = anchor; presentationCaptionMenu.toggleFrom(anchor) }
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
        objectName: "playerViewport"
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
                    label: "← Back"
                    size: "inline"
                    Layout.preferredWidth: 72
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
                width: scene.wide ? Math.min(parent.width, scene.stageHeightLimit * scene.videoAspect +
                                            scene.relatedSideWidth + (scene.hasRelatedSide ? spacing : 0)) : parent.width
                x: (parent.width - width) / 2
                spacing: 24
                Column {
                    id: stageColumn
                    objectName: "playerStageColumn"
                    Layout.fillWidth: true
                    Layout.preferredWidth: scene.wide ? scene.stageHeightLimit * scene.videoAspect : scene.width
                    spacing: 10

                    Item {
                        id: mediaStage
                        objectName: "playerMediaStage"
                        height: Math.max(1, Math.min(scene.stageHeightLimit, parent.width / scene.videoAspect))
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
                            endOfStreamPolicy: VideoOutput.KeepLastFrame
                            anchors.fill: parent
                            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
                        }
                        HoverHandler { id: embeddedHover }
                        MouseArea {
                            anchors.fill: videoSurface
                            onClicked: scene.togglePlayback()
                        }
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
                            surfaceHovered: embeddedHover.hovered
                            menuOpen: playerOptions.visible || captionsMenu.visible
                            chapters: scene.appBridge.playbackChapters
                            player: scene.player
                            volume: scene.volume
                            previews: scene.appBridge.playbackPreviews
                            fallbackArtwork: scene.projection.artwork || ""
                            onPlayPauseRequested: scene.togglePlayback()
                            onSeekRequested: function(seconds) { scene.seekTo(seconds) }
                            onVolumeRequested: function(value) { scene.volumeRequested(value) }
                            onFullscreenRequested: scene.setPresentation("fullscreen")
                            onFloatingRequested: scene.setPresentation("floating")
                            onOptionsRequested: function(anchor) { scene.showOptions(anchor) }
                            onCaptionsRequested: function(anchor) { captionsMenu.anchorItem = anchor; captionsMenu.toggleFrom(anchor) }
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
                    id: relatedSide
                    objectName: "playerRelatedSide"
                    visible: scene.hasRelatedSide
                    Layout.preferredWidth: scene.relatedSideWidth
                    Layout.alignment: Qt.AlignTop
                    spacing: 9
                    Text {
                        text: scene.relatedFallback ? "RECENTLY ADDED" : scene.projection.queued ? "UP NEXT" : "MORE TO WATCH"
                        color: theme.muted
                        font.pixelSize: 12
                        font.bold: true
                    }
                    Column {
                        objectName: "playerRelatedEmptyState"
                        visible: scene.relatedCards.length === 0
                        width: parent.width
                        spacing: 10
                        Text {
                            width: parent.width
                            text: scene.relatedLoading ? "Loading saved media…" : "Add something to watch"
                            color: theme.text
                            font.pixelSize: 16
                            font.bold: true
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            width: parent.width
                            text: scene.relatedLoading ? "Your local suggestions will appear here." : "Save another video in Forge to build your watch list."
                            color: theme.muted
                            font.pixelSize: 13
                            wrapMode: Text.WordWrap
                        }
                        StoneButton {
                            objectName: "playerRelatedAddMedia"
                            visible: !scene.relatedLoading
                            label: "Open Forge"
                            width: Math.min(160, parent.width)
                            onActivated: scene.appBridge.selectHome("Forge")
                        }
                    }
                    Repeater {
                        model: scene.relatedCards.slice(0, 4)
                        StoneField {
                            required property var modelData
                            width: relatedSide.width
                            height: 83
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 8
                                ArtworkImage {
                                    source: modelData.artwork || ""
                                    pending: source.toString().length === 0 &&
                                        scene.appBridge.sizedMediaArtworkState(modelData.owner, 244, 138) === "pending"
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
                visible: !scene.wide
                width: parent.width
                spacing: 8
                Text { text: scene.relatedFallback ? "RECENTLY ADDED" : scene.projection.queued ? "UP NEXT" : "MORE TO WATCH"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Text {
                    visible: scene.relatedCards.length === 0
                    width: parent.width
                    text: scene.relatedLoading ? "Loading saved media…" : "Save another video in Forge to build your watch list."
                    color: theme.muted
                    wrapMode: Text.WordWrap
                }
                StoneButton {
                    objectName: "playerRelatedCompactAddMedia"
                    visible: scene.relatedCards.length === 0 && !scene.relatedLoading
                    label: "Add something to watch"
                    onActivated: scene.appBridge.selectHome("Forge")
                }
                ScrollView {
                    visible: scene.relatedCards.length > 0
                    id: relatedRail
                    objectName: "playerRelatedRail"
                    width: parent.width
                    height: 164
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                    ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                    RailWheelHandler { horizontalView: relatedRail; verticalView: viewport }
                    Row {
                        spacing: 12
                        Repeater {
                            model: scene.relatedCards
                            PlayerThumbnailCard { appBridge: scene.appBridge }
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
                        onActivated: scene.appBridge.seekPlaybackChapter(index)
                    }
                }
            }

            Column {
                objectName: "playerRecentRail"
                visible: !scene.relatedFallback && scene.recentCards.length > 0
                width: parent.width
                spacing: 8
                Text { text: "RECENTLY ADDED"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                ScrollView {
                    id: recentRail
                    width: parent.width
                    height: 164
                    clip: true
                    ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                    ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                    RailWheelHandler {
                        horizontalView: recentRail
                        verticalView: viewport
                    }
                    Row {
                        spacing: 12
                        Repeater {
                            model: scene.recentCards.slice(0, 8)
                            PlayerThumbnailCard { appBridge: scene.appBridge }
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 8
                Row {
                    width: parent.width
                    Text { text: "ABOUT THIS MEDIA"; color: theme.muted; font.pixelSize: 12; font.bold: true; width: parent.width - 36 }
                    StoneButton {
                        objectName: "playerCopyDescriptionButton"
                        label: "⧉"; accessibilityLabel: "Copy description"; size: "inline"
                        width: 32; height: 24
                        onActivated: scene.appBridge.copyLibraryText(scene.projection.owner, "description")
                    }
                }
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
                Row {
                    width: parent.width
                    Text { text: "YOUR DETAILS"; color: theme.muted; font.pixelSize: 12; font.bold: true; width: parent.width - 36 }
                    StoneButton {
                        objectName: "playerCopyTagsButton"
                        label: "⧉"; accessibilityLabel: "Copy tags"; size: "inline"
                        width: 32; height: 24
                        onActivated: scene.appBridge.copyLibraryText(scene.projection.owner, "tags")
                    }
                }
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
            Row {
                width: parent.width
                spacing: 18
                Repeater {
                    model: [
                        { title: "SOURCE DETAILS", facts: scene.projection.source || [] },
                        { title: "OUTPUT DETAILS", facts: scene.projection.output || [] }
                    ]
                    Column {
                        required property var modelData
                        width: (parent.width - parent.spacing) / 2
                        spacing: 8
                        Text { text: modelData.title; color: theme.muted; font.pixelSize: 12; font.bold: true }
                        Repeater {
                            model: modelData.facts
                            RowLayout {
                                required property var modelData
                                width: parent.width
                                Text { text: modelData.label; color: theme.muted; font.pixelSize: 14; Layout.preferredWidth: 160 }
                                Text { text: modelData.value; color: theme.text; font.pixelSize: 14; wrapMode: Text.WrapAnywhere; Layout.fillWidth: true }
                                StoneButton {
                                    visible: modelData.label === "Source URL" && !!modelData.value
                                    label: "⧉"
                                    accessibilityLabel: "Copy source URL"
                                    size: "inline"
                                    Layout.preferredWidth: visible ? 34 : 0
                                    Layout.preferredHeight: 30
                                    onActivated: scene.appBridge.copyPlayerSourceUrl(scene.projection.owner)
                                }
                            }
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
        parent: scene
        scrollViewport: viewport
        player: scene.player
        onTrackRequested: function(index) { scene.selectCaption(index) }
    }
    AnchoredPopup {
        id: playerOptions
        objectName: "playerOptionsMenu"
        parent: scene.presentationMode === "embedded" ? scene : presentationWindow.contentItem
        scrollViewport: scene.presentationMode === "embedded" ? viewport : null
        preferAbove: true
        alignRight: true
        width: 244
        height: 102
        padding: 5
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
