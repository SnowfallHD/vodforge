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
    property string previousPresentationMode: "embedded"
    property string fullscreenReturnMode: "embedded"
    property bool changingPresentationWindow: false
    property bool fullscreenEntered: false
    property int presentationEpoch: 0
    property string displayedOwner: ""
    property bool restoreFillAfterCaptions: false
    property int requestedCaptionTrack: -2
    readonly property var subtitleSession: appBridge.playbackCaptions || null
    readonly property var captionState: subtitleSession ? subtitleSession.state : ({originalAvailable: false, originalEnabled: false, translations: [], translationIndex: -1, message: "No saved captions available"})
    readonly property bool captionsActive: captionState.originalEnabled || captionState.translationIndex >= 0
    readonly property var captionText: {
        const state = captionState
        return subtitleSession ? subtitleSession.textAt(player ? player.position : 0) : ({original: "", translation: ""})
    }
    onCaptionsActiveChanged: captionTrackChanged()

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
    Connections {
        target: scene.player
        ignoreUnknownSignals: true
        function onVideoOutputChanged() { scene.scheduleRetainedFrame() }
    }
    Connections {
        target: scene.player && scene.player.videoOutput ? scene.player.videoOutput.videoSink : null
        function onVideoFrameChanged() {
            scene.appBridge.retainPlaybackFrame(scene.player.videoOutput, scene.displayedOwner)
        }
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
    // Keep the same two-column composition through every supported width.
    // The rail grows continuously; the primary frame receives the remainder.
    readonly property real preferredRelatedSideWidth: Math.min(360, Math.max(270, viewport.availableWidth * 0.27))
    readonly property bool hasRelatedSide: true
    readonly property real relatedSideWidth: preferredRelatedSideWidth
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
    function exitPresentation() {
        if (presentationMode === "fullscreen") {
            presentationMode = fullscreenReturnMode
            appBridge.recordPresentation(fullscreenReturnMode === "embedded" ? "returned" : "floating")
        } else setPresentation("embedded")
    }
    function scheduleNativeFullscreenExit() {
        const epoch = presentationEpoch
        const owner = displayedOwner
        // Defer until native setVisibility completes; bind to this owner/state.
        Qt.callLater(function() {
            if (scene.presentationEpoch === epoch && scene.displayedOwner === owner &&
                    scene.presentationMode === "fullscreen" &&
                    presentationWindow.visibility === Window.Windowed)
                scene.exitPresentation()
        })
    }
    function scheduleEmbeddedRetirement() {
        const epoch = presentationEpoch
        const owner = displayedOwner
        Qt.callLater(function() {
            if (scene.presentationEpoch === epoch && scene.displayedOwner === owner &&
                    scene.presentationMode === "embedded" && presentationWindow.visible)
                presentationWindow.hide()
        })
    }
    function scheduleRetainedFrame() {
        const epoch = presentationEpoch
        const owner = displayedOwner
        const surface = activeVideoSurface
        Qt.callLater(function() {
            if (scene.presentationEpoch === epoch && scene.displayedOwner === owner &&
                    scene.activeVideoSurface === surface)
                scene.appBridge.restorePlaybackFrame(surface, owner)
        })
    }
    function captionTrackChanged() {
        if (!player) return
        // Both text renderers share this player's clock; suppress Qt's single track.
        if (player.activeSubtitleTrack >= 0) player.activeSubtitleTrack = -1
        if (captionsActive && videoFill) {
            videoFill = false
            restoreFillAfterCaptions = true
            appBridge.recordPresentation("caption_fit_applied")
        } else if (!captionsActive && restoreFillAfterCaptions) {
            videoFill = true
            restoreFillAfterCaptions = false
            appBridge.recordPresentation("caption_fill_restored")
        }
    }
    function toggleOriginalCaptions() {
        if (subtitleSession) subtitleSession.toggleOriginal()
    }
    function selectCaption(index) {
        if (subtitleSession) subtitleSession.selectTranslation(index)
    }
    function toggleFill() {
        if (!videoFill && captionsActive) {
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
        presentationEpoch += 1
        if (presentationMode === "fullscreen") {
            fullscreenReturnMode = previousPresentationMode === "floating" ? "floating" : "embedded"
            fullscreenEntered = false
        } else fullscreenEntered = false
        previousPresentationMode = presentationMode
        playerOptions.close()
        captionsMenu.close()
        presentationCaptionMenu.close()
        changingPresentationWindow = true
        if (presentationMode === "embedded") {
            if (presentationWindow.visibility === Window.FullScreen)
                presentationWindow.showNormal()
            presentationWindow.hide()
        } else if (presentationMode === "fullscreen") presentationWindow.showFullScreen()
        else {
            presentationWindow.naturalSizePending = !videoFill
            presentationWindow.showNormal()
            Qt.callLater(presentationWindow.applyNaturalInitialSize)
        }
        changingPresentationWindow = false
        scheduleRetainedFrame()
    }
    onProjectionChanged: {
        const owner = projection.owner || ""
        if (owner !== displayedOwner) {
            displayedOwner = owner
            videoFill = false
            restoreFillAfterCaptions = false
            presentationWindow.naturalSizePending = true
            if (presentationMode === "fullscreen" && fullscreenEntered &&
                    presentationWindow.visibility === Window.Windowed)
                scheduleNativeFullscreenExit()
        }
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
        function enforceMinimumSize() {
            if (width < minimumWidth) width = minimumWidth
            if (height < minimumHeight) height = minimumHeight
        }
        onWidthChanged: Qt.callLater(enforceMinimumSize)
        onHeightChanged: Qt.callLater(enforceMinimumSize)
        onMinimumWidthChanged: Qt.callLater(enforceMinimumSize)
        onMinimumHeightChanged: Qt.callLater(enforceMinimumSize)
        property bool naturalSizePending: true
        property bool naturalSizeLimited: false
        readonly property real displayedAspect: {
            const rect = presentationVideo.contentRect
            return presentationVideo.sourceRect.width > 0 && rect.width > 0 && rect.height > 0
                ? rect.width / rect.height : 16 / 9
        }
        function applyNaturalInitialSize() { naturalSizeTimer.restart() }
        Timer {
            id: naturalSizeTimer
            interval: 16
            onTriggered: presentationWindow.settleNaturalInitialSize()
        }
        function settleNaturalInitialSize() {
            if (!visible || scene.presentationMode !== "floating" || scene.videoFill ||
                    !naturalSizePending || presentationVideo.sourceRect.width <= 0) return
            naturalSizePending = false
            const geometry = scene.appBridge.initialPlayerGeometry(presentationWindow, displayedAspect)
            if (geometry.width > 0 && geometry.height > 0) {
                naturalSizeLimited = geometry.overflow
                width = geometry.width
                height = geometry.height
                x = geometry.x
                y = geometry.y
            } else {
                const naturalWidth = Math.max(minimumWidth, minimumHeight * displayedAspect, width)
                width = Math.round(naturalWidth)
                height = Math.round(naturalWidth / displayedAspect)
            }
        }
        onVisibleChanged: {
            if (visible && scene.presentationMode === "embedded") scene.scheduleEmbeddedRetirement()
        }
        onVisibilityChanged: function(visibility) {
            if (scene.presentationMode === "embedded") {
                if (visible) scene.scheduleEmbeddedRetirement()
                return
            }
            if (scene.presentationMode !== "fullscreen") return
            if (visibility === Window.FullScreen) scene.fullscreenEntered = true
            else if (visibility === Window.Windowed && scene.fullscreenEntered &&
                     !scene.changingPresentationWindow) {
                // A synchronous hide can be undone by the outer native call.
                scene.scheduleNativeFullscreenExit()
            }
        }
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
            onActivated: scene.exitPresentation()
        }
        VideoOutput {
            id: presentationVideo
            objectName: "watchPresentationVideoSurface"
            anchors.fill: parent
            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
            endOfStreamPolicy: VideoOutput.KeepLastFrame
            onContentRectChanged: Qt.callLater(presentationWindow.applyNaturalInitialSize)
            Connections {
                target: presentationVideo.videoSink
                function onVideoFrameChanged() { Qt.callLater(presentationWindow.applyNaturalInitialSize) }
            }
            TapHandler { onTapped: scene.togglePlayback() }
        }
        HoverHandler { id: presentationHover }
        Text {
            objectName: "presentationCaptionText"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 68
            width: parent.width - 36
            text: [scene.captionText.original, scene.captionText.translation].filter(function(value) { return value.length > 0 }).join("\n\n")
            textFormat: Text.PlainText
            visible: text.length > 0
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
            onFullscreenRequested: scene.presentationMode === "fullscreen" ? scene.exitPresentation() : scene.setPresentation("fullscreen")
            onFloatingRequested: scene.setPresentation(scene.presentationMode === "floating" ? "embedded" : "floating")
            onOptionsRequested: function(anchor) { scene.showOptions(anchor) }
            originalCaptionsAvailable: scene.captionState.originalAvailable
            originalCaptionsEnabled: scene.captionState.originalEnabled
            translatedSubtitlesAvailable: scene.captionState.translations.length > 0
            translatedSubtitlesEnabled: scene.captionState.translationIndex >= 0
            captionStatus: scene.captionState.message
            onCaptionsRequested: scene.toggleOriginalCaptions()
            onSubtitlesRequested: function(anchor) { presentationCaptionMenu.anchorItem = anchor; presentationCaptionMenu.toggleFrom(anchor) }
            onPreviewRequested: function(seconds) { scene.appBridge.hoverPlaybackPreview(seconds) }
        }
        CaptionTracks {
            id: presentationCaptionMenu
            objectName: "presentationCaptionsMenu"
            parent: presentationWindow.contentItem
            tracks: scene.captionState.translations
            selectedIndex: scene.captionState.translationIndex
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
                width: Math.min(parent.width, scene.stageHeightLimit * scene.videoAspect +
                                scene.relatedSideWidth + spacing)
                x: 0
                spacing: 24
                Column {
                    id: stageColumn
                    objectName: "playerStageColumn"
                    Layout.fillWidth: true
                    Layout.preferredWidth: Math.max(1, parent.width - scene.relatedSideWidth - parent.spacing)
                    Layout.minimumWidth: 0
                    spacing: 10

                    Item {
                        id: mediaStage
                        objectName: "playerMediaStage"
                        height: Math.max(1, Math.min(scene.stageHeightLimit, parent.width / scene.videoAspect))
                        width: Math.min(parent.width, height * scene.videoAspect)
                        x: 0
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
                            visible: scene.presentationMode === "embedded"
                            endOfStreamPolicy: VideoOutput.KeepLastFrame
                            anchors.fill: parent
                            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
                        }
                        HoverHandler { id: embeddedHover }
                        MouseArea {
                            anchors.fill: videoSurface
                            enabled: scene.presentationMode === "embedded"
                            onClicked: scene.togglePlayback()
                        }
                        Text {
                            objectName: "embeddedCaptionText"
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 110
                            width: parent.width - 28
                            text: [scene.captionText.original, scene.captionText.translation].filter(function(value) { return value.length > 0 }).join("\n\n")
                            textFormat: Text.PlainText
                            visible: scene.presentationMode === "embedded" && text.length > 0
                            color: "white"
                            style: Text.Outline
                            styleColor: "#09090d"
                            font.pixelSize: 18
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }
                        Rectangle {
                            objectName: "inlinePlaybackElsewhere"
                            anchors.fill: parent
                            visible: scene.presentationMode !== "embedded"
                            color: "#b309090d"
                            StoneButton {
                                objectName: "inlinePlaybackReturn"
                                anchors.centerIn: parent
                                width: Math.min(parent.width - 24, 240)
                                height: 42
                                label: scene.presentationMode === "fullscreen" && scene.fullscreenReturnMode === "embedded"
                                    ? "Exit fullscreen" : "Exit external player"
                                accessibilityLabel: label + "; return playback to Watch"
                                onActivated: scene.setPresentation("embedded")
                            }
                        }
                        PlayerOverlay {
                            id: embeddedOverlay
                            presentationAvailable: scene.presentationMode === "embedded"
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
                            originalCaptionsAvailable: scene.captionState.originalAvailable
                            originalCaptionsEnabled: scene.captionState.originalEnabled
                            translatedSubtitlesAvailable: scene.captionState.translations.length > 0
                            translatedSubtitlesEnabled: scene.captionState.translationIndex >= 0
                            captionStatus: scene.captionState.message
                            onCaptionsRequested: scene.toggleOriginalCaptions()
                            onSubtitlesRequested: function(anchor) { captionsMenu.anchorItem = anchor; captionsMenu.toggleFrom(anchor) }
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
                    Layout.minimumWidth: scene.relatedSideWidth
                    Layout.maximumWidth: scene.relatedSideWidth
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
                        Repeater {
                            objectName: "playerSidePlaceholderRepeater"
                            model: 2
                            WatchPlaceholderCard {
                                width: relatedSide.width
                                height: width * 9 / 16 + 34
                                sectionTitle: "Recently Added"
                            }
                        }
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
                                    Layout.preferredHeight: 92 * 9 / 16
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
                visible: (!scene.relatedFallback && scene.recentCards.length > 0) || scene.relatedCards.length === 0
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
                            model: scene.relatedFallback ? [] : scene.recentCards.slice(0, 8)
                            PlayerThumbnailCard { appBridge: scene.appBridge }
                        }
                        Repeater {
                            objectName: "playerBottomPlaceholderRepeater"
                            model: scene.relatedCards.length === 0 ? Math.max(1, Math.ceil(recentRail.width / 220)) : 0
                            WatchPlaceholderCard {
                                width: 207
                                height: 150
                                sectionTitle: "Recently Added"
                            }
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
        tracks: scene.captionState.translations
        selectedIndex: scene.captionState.translationIndex
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
