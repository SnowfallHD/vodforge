import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
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
        onClosing: function(close) {
            close.accepted = false
            scene.setPresentation("embedded")
        }
        VideoOutput {
            id: presentationVideo
            objectName: "watchPresentationVideoSurface"
            anchors.fill: parent
            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
        }
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
        Row {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            anchors.margins: 18
            spacing: 8
            StoneButton {
                label: "Return to Watch"
                transientMaterial: false
                width: 150; height: 40
                onActivated: scene.setPresentation("embedded")
            }
            StoneButton {
                label: scene.player && scene.player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                transientMaterial: false
                width: 82; height: 40
                onActivated: {
                    if (!scene.player) return
                    if (scene.player.playbackState === MediaPlayer.PlayingState) scene.player.pause()
                    else scene.player.play()
                }
            }
            StoneButton {
                label: scene.videoFill ? "Fit" : "Fill"
                transientMaterial: false
                width: 68; height: 40
                onActivated: scene.toggleFill()
            }
            StoneButton {
                objectName: "presentationCaptionsButton"
                label: "CC"
                accessibilityLabel: "Captions"
                transientMaterial: false
                width: 44; height: 40
                onActivated: presentationCaptionMenu.open()
            }
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
                width: parent.width
                spacing: 24
                Column {
                    id: stageColumn
                    objectName: "playerStageColumn"
                    Layout.fillWidth: true
                    Layout.preferredWidth: scene.wide ? Math.max(320, scene.width - 334) : scene.width
                    spacing: 10

                    Item {
                        id: mediaStage
                        objectName: "playerMediaStage"
                        width: parent.width
                        height: Math.max(180, Math.min(390, width * 9 / 16, scene.height - 205))
                        Rectangle { anchors.fill: parent; color: "#09090d" }
                        VideoOutput {
                            id: videoSurface
                            objectName: "watchVideoSurface"
                            anchors.fill: parent
                            fillMode: scene.videoFill ? VideoOutput.PreserveAspectCrop : VideoOutput.PreserveAspectFit
                        }
                        Text {
                            objectName: "embeddedCaptionText"
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 14
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
                    }
                    Item {
                        id: heatmapTrack
                        objectName: "watchHeatmap"
                        visible: scene.appBridge.playbackHeatmap.length > 0 && scene.player && scene.player.duration > 0
                        width: parent.width
                        height: visible ? 18 : 0
                        clip: true
                        Repeater {
                            model: scene.appBridge.playbackHeatmap
                            Rectangle {
                                required property var modelData
                                x: Math.max(0, Math.min(heatmapTrack.width,
                                    modelData.start_time * heatmapTrack.width * 1000 / Math.max(1, scene.player ? scene.player.duration : 0)))
                                width: Math.max(1, (modelData.end_time - modelData.start_time) *
                                    heatmapTrack.width * 1000 / Math.max(1, scene.player ? scene.player.duration : 0))
                                height: Math.max(2, 16 * modelData.value)
                                y: heatmapTrack.height - height
                                color: theme.accent
                                opacity: 0.72
                            }
                        }
                    }
                    Slider {
                        Accessible.name: "Playback position"
                        width: parent.width
                        from: 0
                        to: Math.max(1, scene.player ? scene.player.duration : 0)
                        value: scene.player ? scene.player.position : 0
                        onMoved: scene.appBridge.manualPlaybackSeek(value / 1000)
                        background: StoneField { x: 0; y: parent.height / 2 - 5; width: parent.width; height: 10 }
                        handle: StoneButton { x: parent.visualPosition * (parent.width - width); y: parent.height / 2 - height / 2; width: 22; height: 22; label: ""; interactive: false; transientMaterial: false }
                    }
                    RowLayout {
                        objectName: "playerTransportRow"
                        width: parent.width
                        StoneButton {
                            label: scene.player && scene.player.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                            transientMaterial: false
                            Layout.preferredWidth: 95
                            Layout.preferredHeight: 40
                            onActivated: {
                                if (!scene.player) return
                                if (scene.player.playbackState === MediaPlayer.PlayingState) scene.player.pause()
                                else scene.player.play()
                            }
                        }
                        Text {
                            text: Math.floor((scene.player ? scene.player.position : 0) / 1000) + "s / " +
                                  Math.floor((scene.player ? scene.player.duration : 0) / 1000) + "s"
                            color: theme.muted
                            font.pixelSize: 14
                        }
                        StoneButton {
                            label: "Full screen"
                            transientMaterial: false
                            Layout.preferredWidth: 118
                            onActivated: scene.setPresentation("fullscreen")
                        }
                        StoneButton {
                            label: "Floating"
                            transientMaterial: false
                            Layout.preferredWidth: 100
                            onActivated: scene.setPresentation("floating")
                        }
                        StoneButton {
                            objectName: "playerFillButton"
                            label: scene.videoFill ? "Fit" : "Fill"
                            transientMaterial: false
                            Layout.preferredWidth: 68
                            onActivated: scene.toggleFill()
                        }
                        StoneButton {
                            objectName: "playerCaptionsButton"
                            label: "CC"
                            accessibilityLabel: "Captions"
                            transientMaterial: false
                            Layout.preferredWidth: 44
                            Layout.preferredHeight: 40
                            onActivated: captionsMenu.open()
                        }
                        Item { Layout.fillWidth: true }
                        Text { text: "Volume"; color: theme.muted; font.pixelSize: 14 }
                        Slider {
                            Accessible.name: "Volume"
                            Layout.preferredWidth: 150
                            from: 0; to: 1; value: scene.volume
                            onMoved: scene.volumeRequested(value)
                            background: StoneField { x: 0; y: parent.height / 2 - 5; width: parent.width; height: 10 }
                            handle: StoneButton { x: parent.visualPosition * (parent.width - width); y: parent.height / 2 - height / 2; width: 22; height: 22; label: ""; interactive: false; transientMaterial: false }
                        }
                    }
                    Text {
                        width: parent.width
                        text: scene.player && scene.player.errorString.length ? scene.player.errorString : ""
                        color: theme.muted
                        font.pixelSize: 14
                        visible: text.length > 0
                        wrapMode: Text.WordWrap
                    }
                }

                Column {
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
                                Image {
                                    source: modelData.artwork || ""
                                    Layout.preferredWidth: 92
                                    Layout.preferredHeight: 58
                                    fillMode: Image.PreserveAspectCrop
                                    smooth: true
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
                objectName: "watchMoments"
                visible: scene.appBridge.playbackPreviews.length > 0
                width: parent.width
                spacing: 8
                Text { text: "MOMENTS"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Text {
                    text: "Select a moment to jump there."
                    color: theme.muted
                    font.pixelSize: 13
                }
                Flow {
                    width: parent.width
                    spacing: 10
                    Repeater {
                        model: scene.appBridge.playbackPreviews
                        StoneField {
                            required property var modelData
                            width: Math.min(192, Math.max(140, (scene.width - 40) / 5))
                            height: 145
                            Column {
                                anchors.fill: parent
                                anchors.margins: 7
                                spacing: 5
                                Image {
                                    width: parent.width
                                    height: 90
                                    source: modelData.image || ""
                                    fillMode: Image.PreserveAspectFit
                                    smooth: true
                                    Text {
                                        anchors.centerIn: parent
                                        visible: !modelData.image
                                        text: modelData.status || ""
                                        color: theme.muted
                                        font.pixelSize: 12
                                    }
                                }
                                StoneButton {
                                    width: parent.width
                                    height: 32
                                    size: "inline"
                                    label: Math.floor(modelData.position / 60) + ":" +
                                        ("0" + Math.floor(modelData.position % 60)).slice(-2)
                                    onActivated: scene.appBridge.manualPlaybackSeek(modelData.position)
                                }
                            }
                        }
                    }
                }
            }

            Column {
                visible: (scene.projection.recent || []).length > 1
                width: parent.width
                spacing: 8
                Text { text: "RECENTLY ADDED"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Row {
                    spacing: 10
                    Repeater {
                        model: (scene.projection.recent || []).slice(0, 5)
                        StoneButton {
                            required property var modelData
                            label: modelData.title
                            width: Math.min(190, (scene.width - 40) / 5)
                            height: 40
                            size: "inline"
                            onActivated: scene.appBridge.playPlayerRelated(modelData.owner)
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
}
