import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtMultimedia

Window {
    id: window
    visible: true
    width: 1100
    height: 740
    x: 30
    y: 30
    minimumWidth: 820
    minimumHeight: 560
    title: "VODForge"
    color: theme.bg
    property real playerVolume: 0.8
    property string pendingRelinkOwner: ""
    property string missingAction: ""
    property string pendingRelinkFolderPath: ""
    property var mediaPlayer: playerLoader.item
    readonly property var selectedForgeRun: bridge.forgeSelection
    readonly property bool showingForgePreview: selectedForgeRun.kind === "preview"
    readonly property string forgeDisplayType: selectedForgeRun.type || window.outputFormat
    readonly property bool playerSurfaceBound: mediaPlayer && mediaPlayer.videoOutput === playerScene.activeVideoSurface
    property int pendingPlaybackGeneration: -1
    onClosing: function(close) {
        if (bridge.running) {
            bridge.cancel()
            close.accepted = false
        }
        if (bridge.localRunning) {
            bridge.cancelLocalConversion()
            close.accepted = false
        }
    }

    Component {
        id: mediaPlayerComponent
        MediaPlayer {
            objectName: "watchMediaPlayer"
            property int generation: 0
            audioOutput: AudioOutput { volume: window.playerVolume }
            videoOutput: playerScene.activeVideoSurface
            function reportProgress() {
                var status = "Ready"
                if (error !== MediaPlayer.NoError) status = "Failed"
                else if (mediaStatus === MediaPlayer.EndOfMedia) status = "Ended"
                else if (playbackState === MediaPlayer.PlayingState) status = "Playing"
                else if (playbackState === MediaPlayer.PausedState) status = "Paused"
                bridge.observePlayback(position / 1000, duration / 1000, status, generation)
            }
            onPositionChanged: reportProgress()
            onDurationChanged: reportProgress()
            onPlaybackStateChanged: reportProgress()
            onMediaStatusChanged: reportProgress()
            onErrorChanged: reportProgress()
            onActiveSubtitleTrackChanged: playerScene.captionTrackChanged()
        }
    }
    Loader {
        id: playerLoader
        sourceComponent: mediaPlayerComponent
        onLoaded: {
            if (window.pendingPlaybackGeneration < 0) return
            item.generation = window.pendingPlaybackGeneration
            window.pendingPlaybackGeneration = -1
            item.source = bridge.playbackUrl
            item.play()
        }
    }
    Connections {
        target: bridge
        function onAnalyticsPromptRequested() { analyticsPopup.open() }
        function onSupportRequested() {
            supportPopup.reason = "Select one…"
            supportPopup.stars = 0
            supportPopup.reply = false
            supportPopup.includeDiagnostics = false
            supportPopup.includeVideoUrl = false
            supportMessage.text = ""
            supportEmail.text = ""
            supportName.text = ""
            supportPopup.open()
        }
        function onEditorialRequested() { editorialPopup.open() }
        function onFileActionRequested() { fileActionPopup.open() }
        function onSourceAccepted() { urlInput.text = "" }
        function onSourcePrepared(url) { urlInput.text = url }
        function onMissingMediaRequested() { missingMediaPopup.open() }
        function onFolderRelinkRequested(path) {
            window.pendingRelinkFolderPath = path
            relinkFolderDialog.open()
        }
        function onPlaybackRequested(generation) {
            // Retire the old provider object before a queued item opens. Any
            // late signal carries the old generation and cannot advance it.
            window.pendingPlaybackGeneration = generation
            playerLoader.sourceComponent = null
            playerLoader.sourceComponent = mediaPlayerComponent
        }
        function onPlaybackSeekRequested(position) {
            if (window.mediaPlayer) mediaPlayer.setPosition(position * 1000)
        }
    }
    EditorialPopup {
        id: editorialPopup
        parent: window.contentItem
        slides: bridge.editorialSlides
        heading: bridge.editorialHeading
        finishLabel: bridge.editorialFinishLabel
        onAcknowledged: function(tryIt) {
            bridge.dismissEditorial(tryIt)
            if (tryIt) settingsPopup.open()
        }
    }
    Timer {
        interval: 700
        running: true
        repeat: true
        onTriggered: bridge.checkEditorial(
            window.active && !analyticsPopup.visible && !editorialPopup.visible &&
            !helpMenu.visible && !supportPopup.visible && !supportReasonMenu.visible &&
            !supportDiagnostics.visible && !libraryItemPopup.visible &&
            !fileActionPopup.visible && !libraryRemovalPopup.visible &&
            !collectionPopup.visible && !categoryPopup.visible &&
            !annotationPopup.visible && !mp3OptionsPopup.visible && !settingsPopup.visible &&
            !updatePopup.visible && !accessPopup.visible &&
            !localConversionPopup.visible && !localProfilePopup.visible &&
            !formatMenu.visible && !optionsMenu.visible)
    }
    Popup {
        id: helpMenu
        objectName: "helpMenu"
        x: Math.max(0, window.width - width - window.gutter)
        y: window.gutter + 55
        width: 235
        height: 152
        padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 3
            StoneButton {
                width: parent.width; height: 46
                label: "Help & feedback"
                onActivated: { helpMenu.close(); bridge.openSupport("feedback") }
            }
            StoneButton {
                width: parent.width; height: 46
                label: "Write a review"
                onActivated: { helpMenu.close(); bridge.openSupport("review") }
            }
            StoneButton {
                width: parent.width; height: 46
                label: "Welcome tour"
                onActivated: { helpMenu.close(); bridge.openWelcomeTour() }
            }
        }
    }
    Popup {
        id: supportPopup
        objectName: "supportPopup"
        property string reason: "Select one…"
        property int stars: 0
        property bool reply: false
        property bool includeDiagnostics: false
        property bool includeVideoUrl: false
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(580, window.width - 18)
        height: Math.min(bridge.supportKind === "feedback" && reply ? 580 : bridge.supportKind === "feedback" ? 510 : 480, window.height - 18)
        padding: 18
        modal: true
        closePolicy: bridge.supportBusy ? Popup.NoAutoClose : Popup.CloseOnEscape
        background: StoneField {}
        onClosed: bridge.closeSupport()
        ColumnLayout {
            anchors.fill: parent
            spacing: 9
            Text {
                text: bridge.supportKind === "feedback" ? "Help & feedback" : "How’s VODForge working for you?"
                color: theme.text; font.pixelSize: 24; font.bold: true
                Layout.fillWidth: true; wrapMode: Text.WordWrap
            }
            Text {
                text: bridge.supportKind === "feedback" ?
                      "Send a focused report directly to VODForge. This does not enable analytics." :
                      "Your honest rating helps us improve VODForge."
                color: theme.muted; font.pixelSize: 14
                Layout.fillWidth: true; wrapMode: Text.WordWrap
            }
            ScrollView {
                id: supportBody
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: supportBody.availableWidth
                    spacing: 8
                    StoneButton {
                        visible: bridge.supportKind === "feedback"
                        label: supportPopup.reason + "  ▾"
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onActivated: supportReasonMenu.open()
                    }
                    RowLayout {
                        visible: bridge.supportKind === "review"
                        Layout.fillWidth: true
                        Repeater {
                            model: 5
                            StoneButton {
                                required property int index
                                label: index < supportPopup.stars ? "★" : "☆"
                                accessibilityLabel: (index + 1) + " stars"
                                selected: index < supportPopup.stars
                                Layout.preferredWidth: 48; Layout.preferredHeight: 42
                                enabled: !bridge.supportBusy && !bridge.supportSent
                                onActivated: supportPopup.stars = index + 1
                            }
                        }
                    }
                    Text {
                        text: bridge.supportKind === "feedback" ? "Message" : "Comment (optional)"
                        color: theme.text; font.pixelSize: 14
                    }
                    TextArea {
                        id: supportMessage
                        objectName: "supportMessage"
                        Layout.fillWidth: true; Layout.preferredHeight: 112
                        color: theme.text; font.pixelSize: 15
                        wrapMode: TextEdit.Wrap
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        background: StoneField {}
                    }
                    Text {
                        text: supportMessage.text.length + " / " + (bridge.supportKind === "feedback" ? 2000 : 1000)
                        color: theme.muted; font.pixelSize: 12
                        Layout.alignment: Qt.AlignRight
                    }
                    StoneButton {
                        visible: bridge.supportKind === "feedback"
                        label: "I’d like a reply"
                        selected: supportPopup.reply
                        Layout.preferredWidth: 170; Layout.preferredHeight: 38
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onActivated: supportPopup.reply = !supportPopup.reply
                    }
                    TextField {
                        id: supportEmail
                        visible: bridge.supportKind === "feedback" && supportPopup.reply
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        placeholderText: "Reply email (optional)"
                        placeholderTextColor: theme.muted; color: theme.text
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        background: StoneField {}
                    }
                    Text {
                        visible: bridge.supportKind === "review"
                        text: "Display name (optional; otherwise Anonymous)"
                        color: theme.muted; font.pixelSize: 13
                    }
                    TextField {
                        id: supportName
                        visible: bridge.supportKind === "review"
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        placeholderText: "Display name"
                        placeholderTextColor: theme.muted; color: theme.text
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        background: StoneField {}
                    }
                    Text {
                        visible: bridge.supportKind === "review"
                        text: "Your rating, comment, and display name may appear publicly on the VODForge website. Leave your name blank to appear as Anonymous."
                        color: theme.muted; font.pixelSize: 13
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                    }
                    StoneButton {
                        visible: bridge.supportKind === "feedback" && !!bridge.supportContext.diagnostics
                        label: "Include recent diagnostics"
                        selected: supportPopup.includeDiagnostics
                        Layout.preferredWidth: 225; Layout.preferredHeight: 38
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onActivated: supportPopup.includeDiagnostics = !supportPopup.includeDiagnostics
                    }
                    StoneButton {
                        visible: bridge.supportKind === "feedback" && !!bridge.supportContext.diagnostics
                        label: "Review diagnostics"
                        size: "inline"
                        Layout.preferredWidth: 165
                        onActivated: supportDiagnostics.open()
                    }
                    StoneButton {
                        visible: bridge.supportKind === "feedback" && !!bridge.supportContext.videoUrl
                        label: "Include the public video URL"
                        selected: supportPopup.includeVideoUrl
                        Layout.preferredWidth: 245; Layout.preferredHeight: 38
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onActivated: supportPopup.includeVideoUrl = !supportPopup.includeVideoUrl
                    }
                }
            }
            Text {
                text: bridge.supportStatus
                color: theme.muted; font.pixelSize: 13
                Layout.fillWidth: true; wrapMode: Text.WordWrap
            }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    label: bridge.supportSent ? "Done" : bridge.supportKind === "feedback" ? "Cancel" : "No thanks"
                    Layout.preferredWidth: 98; Layout.preferredHeight: 40
                    enabled: !bridge.supportBusy
                    onActivated: supportPopup.close()
                }
                Item { Layout.fillWidth: true }
                StoneButton {
                    visible: !bridge.supportSent
                    label: bridge.supportKind === "feedback" ? "Send feedback" : "Submit public review"
                    emphasized: true
                    Layout.preferredWidth: bridge.supportKind === "feedback" ? 150 : 195
                    Layout.preferredHeight: 40
                    enabled: !bridge.supportBusy
                    onActivated: bridge.submitSupport({
                        reason: supportPopup.reason,
                        stars: supportPopup.stars,
                        message: supportMessage.text,
                        reply: supportPopup.reply,
                        email: supportEmail.text,
                        diagnostics: supportPopup.includeDiagnostics,
                        videoUrl: supportPopup.includeVideoUrl,
                        name: supportName.text
                    })
                }
            }
        }
    }
    Popup {
        id: supportReasonMenu
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: 290; height: 238; padding: 3
        modal: true
        background: StoneField {}
        Column {
            anchors.fill: parent; spacing: 2
            Repeater {
                model: ["Download problem", "Playback problem", "Interface problem", "Suggestion", "Other"]
                StoneButton {
                    required property string modelData
                    width: parent.width; height: 44
                    label: modelData
                    selected: modelData === supportPopup.reason
                    onActivated: { supportPopup.reason = modelData; supportReasonMenu.close() }
                }
            }
        }
    }
    Popup {
        id: supportDiagnostics
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(580, window.width - 24)
        height: Math.min(430, window.height - 24)
        padding: 16; modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            Text { text: "Review diagnostics"; color: theme.text; font.pixelSize: 22; font.bold: true }
            ScrollView {
                id: diagnosticsBody
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                Text {
                    text: bridge.supportContext.diagnostics + (bridge.supportContext.videoUrl ? "\n\nOptional video URL: " + bridge.supportContext.videoUrl : "")
                    color: theme.text; font.pixelSize: 14
                    width: diagnosticsBody.availableWidth; wrapMode: Text.WrapAnywhere
                }
            }
            StoneButton { label: "Done"; Layout.alignment: Qt.AlignRight; Layout.preferredWidth: 82; onActivated: supportDiagnostics.close() }
        }
    }
    Popup {
        id: analyticsPopup
        objectName: "analyticsConsentPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(440, window.width - 40)
        height: 265
        padding: 20
        modal: true
        closePolicy: Popup.NoAutoClose
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text { text: "Help improve VODForge"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text {
                text: "Share private, anonymous usage events to help us fix errors and improve the app. You can change this in Settings."
                color: theme.text
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            StoneButton { label: "Privacy details"; Layout.preferredWidth: 160; Layout.preferredHeight: 38; onActivated: bridge.openPrivacy() }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "No thanks"; Layout.preferredWidth: 115; Layout.preferredHeight: 40; onActivated: { if (bridge.chooseAnalytics(false)) analyticsPopup.close() } }
                StoneButton { label: "Share analytics"; Layout.preferredWidth: 150; Layout.preferredHeight: 40; onActivated: { if (bridge.chooseAnalytics(true)) analyticsPopup.close() } }
            }
        }
    }
    FolderDialog {
        id: outputFolderDialog
        title: "Choose output folder"
        onAccepted: bridge.chooseOutputUrl(selectedFolder)
    }
    FolderDialog {
        id: libraryMoveFolderDialog
        title: "Move saved media to"
        onAccepted: {
            if (bridge.startFileActions("move", window.pendingFileOwners, selectedFolder)) {
                fileActionPopup.open()
            }
        }
    }
    FileDialog {
        id: localAudioDialog
        title: "Choose MP3 audio"
        nameFilters: ["MP3 audio (*.mp3)"]
        onAccepted: bridge.setLocalAudioUrl(selectedFile)
    }
    FileDialog {
        id: localImageDialog
        title: "Choose still image"
        nameFilters: ["Images (*.jpg *.jpeg *.png *.webp)"]
        onAccepted: bridge.setLocalImageUrl(selectedFile)
    }
    FileDialog {
        id: mp3CoverDialog
        title: "Choose MP3 cover image"
        nameFilters: ["Images (*.jpg *.jpeg *.png *.webp)"]
        onAccepted: bridge.setMp3CoverUrl(selectedFile)
    }
    FileDialog {
        id: urlListDialog
        title: "Choose VODForge URL list"
        nameFilters: ["Text files (*.txt)", "All files (*)"]
        onAccepted: bridge.loadBatchUrl(selectedFile)
    }
    FileDialog {
        id: libraryImportDialog
        title: "Add media to Library"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Video and audio (*.mp4 *.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus)"]
        onAccepted: bridge.importMedia(selectedFiles)
    }
    FileDialog {
        id: cookieFileDialog
        title: "Choose YouTube cookies.txt"
        nameFilters: ["Cookie text files (*.txt)", "All files (*)"]
        onAccepted: bridge.setCookieFileUrl(selectedFile)
    }
    FileDialog {
        id: relinkFileDialog
        title: "Find this saved media file"
        nameFilters: ["Video and audio (*.mp4 *.mp3 *.m4a *.aac *.wav *.flac *.ogg *.opus *.webm *.mkv *.mov)", "All files (*)"]
        onAccepted: {
            if (bridge.beginRelink(window.pendingRelinkOwner, selectedFile)) {
                missingMediaPopup.close()
                libraryItemPopup.close()
                relinkPopup.open()
            }
        }
    }
    FolderDialog {
        id: relinkFolderDialog
        title: "Choose this folder's new location"
        onAccepted: {
            if (bridge.beginFolderRelink(window.pendingRelinkFolderPath, selectedFolder))
                relinkPopup.open()
            window.pendingRelinkFolderPath = ""
        }
        onRejected: window.pendingRelinkFolderPath = ""
    }
    FolderDialog {
        id: missingFolderDialog
        title: "Choose a download folder for this saved item"
        onAccepted: {
            var accepted = window.missingAction === "redownload"
                ? bridge.redownloadMissingTo(selectedFolder)
                : bridge.openMissingInForge(selectedFolder)
            if (accepted) missingMediaPopup.close()
        }
    }
    ColorDialog {
        id: accentColorDialog
        title: "Choose VODForge accent color"
        selectedColor: bridge.customAccent
        onAccepted: bridge.setAppearance("Custom accent", selectedColor.toString())
    }

    Image {
        id: artwork
        objectName: "fullCoverArtwork"
        anchors.fill: parent
        source: "image://vodforge/backdrop/r" + bridge.themeRevision
        fillMode: Image.PreserveAspectCrop
        smooth: true
        cache: true
    }

    property int gutter: width < 960 ? 22 : 38
    property bool compactHeight: height < 640
    property int rowGap: compactHeight ? 8 : 14
    property string outputFormat: bridge.outputFormat
    property string selectedSavedOwner: ""
    property var pendingFileOwners: []

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: window.gutter
        spacing: window.rowGap

        Item {
            id: focusHeader
            Layout.fillWidth: true
            Layout.preferredHeight: stacked ? 100 : 52
            readonly property bool compact: window.width < 960
            readonly property int brandWidth: compact ? 150 : 196
            readonly property int searchWidth: compact ? 150 : 220
            readonly property int navWidth: navigationRow.implicitWidth
            readonly property int utilityWidth: searchWidth + 64 + 46 + 20
            readonly property bool stacked: brandWidth + navWidth + utilityWidth + 20 > width

            Row {
                id: brandRow
                x: 0; y: 8; spacing: 7
                Image {
                    source: assetUrl + "brand/vf-mark.png"
                    width: 32; height: 32
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                Image {
                    source: assetUrl + "brand/vf-name.png"
                    width: focusHeader.compact ? 107 : 145
                    height: 27
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
            }
            Row {
                id: navigationRow
                x: focusHeader.stacked ? 0 : focusHeader.brandWidth + 10
                y: focusHeader.stacked ? 56 : 6
                spacing: 10
                Repeater {
                    model: ["Forge", "Library", "Watch", "Activity"]
                    StoneButton {
                        required property string modelData
                        label: modelData
                        selected: bridge.selection === modelData
                        icon: "image://vodforge/icon/" + (
                            modelData === "Forge" ? "download-20.png" :
                            modelData === "Library" ? "folder-20.png" :
                            modelData === "Watch" ? "play.png" : "activity-20.png") + "/r" + bridge.themeRevision
                        width: Math.max(86, implicitWidth)
                        height: implicitHeight
                        onActivated: bridge.select(modelData)
                    }
                }
            }
            Row {
                id: utilitiesRow
                anchors.right: parent.right
                y: 6
                spacing: 10
                StoneField {
                    width: focusHeader.searchWidth
                    height: 40
                    focused: searchInput.activeFocus
                    TextField {
                        id: searchInput
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 12
                        placeholderText: "Search your library…"
                        color: theme.text
                        placeholderTextColor: theme.muted
                        background: Item {}
                        font.pixelSize: 15
                        onTextChanged: bridge.setLibrarySearch(text)
                        onAccepted: bridge.select("Library")
                    }
                }
                StoneButton {
                    label: "Help"
                    accessibilityLabel: "Help"
                    width: 64; height: 40
                    onActivated: helpMenu.open()
                }
                StoneButton {
                    label: "⚙"
                    accessibilityLabel: "Settings"
                    width: 46; height: 40
                    onActivated: settingsPopup.open()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: theme.border
        }

        ColumnLayout {
            visible: bridge.selection === "Forge"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: window.rowGap

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 52
                spacing: 12
                StoneField {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    focused: urlInput.activeFocus
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 9
                        Text {
                            text: "🔗"
                            color: theme.action
                            font.pixelSize: 17
                            Layout.preferredWidth: 25
                        }
                        TextField {
                            id: urlInput
                            objectName: "forgeUrlInput"
                            Layout.fillWidth: true
                            placeholderText: "Paste a video URL"
                            color: theme.text
                            placeholderTextColor: theme.muted
                            background: Item {}
                            font.pixelSize: 16
                            onAccepted: bridge.submit(text, window.outputFormat)
                        }
                        Rectangle {
                            Layout.preferredWidth: 1
                            Layout.preferredHeight: 26
                            color: theme.border
                        }
                        StoneButton {
                            label: window.outputFormat + "  ▾"
                            Layout.preferredWidth: 92
                            Layout.preferredHeight: 38
                            onActivated: formatMenu.open()
                        }
                    }
                }
                StoneButton {
                    label: "Options"
                    Layout.preferredWidth: 100
                    Layout.preferredHeight: 44
                    onActivated: window.outputFormat === "MP3" ? mp3OptionsPopup.open() : optionsMenu.open()
                }
                StoneButton {
                    label: bridge.running ? "Queue" : "Download"
                    emphasized: true
                    Layout.preferredWidth: 134
                    Layout.preferredHeight: 44
                    onActivated: bridge.submit(urlInput.text, window.outputFormat)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: window.compactHeight ? 42 : 48
                spacing: 12
                StoneButton {
                    label: bridge.batchSummary === "No URL list loaded" ? "Load URL list" : "List loaded"
                    Layout.preferredWidth: 116
                    Layout.preferredHeight: 42
                    onActivated: urlListDialog.open()
                }
                Text {
                    text: "Save to"
                    color: theme.muted
                    font.pixelSize: 15
                    Layout.leftMargin: 7
                }
                StoneField {
                    Layout.preferredWidth: Math.min(250, Math.max(150, window.width * 0.23))
                    Layout.preferredHeight: 42
                    interactive: true
                    accessibilityLabel: "Choose output folder"
                    onActivated: outputFolderDialog.open()
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 8
                        Image {
                            source: "image://vodforge/icon/folder-20.png/r" + bridge.themeRevision
                            Layout.preferredWidth: 18
                            Layout.preferredHeight: 18
                            fillMode: Image.PreserveAspectFit
                        }
                        Text {
                            text: bridge.outputPath
                            color: theme.text
                            font.pixelSize: 15
                            elide: Text.ElideLeft
                            Layout.fillWidth: true
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                Text { text: "Have local audio?"; color: theme.muted; font.pixelSize: 15 }
                StoneButton {
                    label: "Create video"
                    Layout.preferredWidth: 132
                    Layout.preferredHeight: 42
                    onActivated: localConversionPopup.open()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: window.compactHeight ? 70 : 128
                Layout.topMargin: window.compactHeight ? 4 : 16
                spacing: window.compactHeight ? 16 : 28
                Image {
                    source: assetUrl + "brand/icon-180.png"
                    Layout.preferredWidth: window.compactHeight ? 48 : 68
                    Layout.preferredHeight: window.compactHeight ? 48 : 68
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    spacing: window.compactHeight ? 3 : 7
                    Text {
                        objectName: "forgeSelectedTitle"
                        text: window.selectedForgeRun.title || "Ready for a new run"
                        color: theme.text
                        font.pixelSize: window.compactHeight ? 21 : 24
                        font.bold: true
                    }
                    Text {
                        objectName: "forgeSelectedStatus"
                        text: window.selectedForgeRun.status ||
                              "Paste a video URL above, then press Return to begin."
                        color: theme.muted
                        font.pixelSize: window.compactHeight ? 13 : 15
                    }
                    Text {
                        text: window.selectedForgeRun.detail ||
                              (window.selectedForgeRun.kind === "active" ? bridge.quality + "  ·  " + bridge.exportModeLabel : "")
                        color: theme.muted
                        font.pixelSize: window.compactHeight ? 13 : 15
                    }
                    StoneButton {
                        visible: window.showingForgePreview && bridge.forgePreview.canStart
                        label: "Start download"
                        Layout.preferredWidth: 142
                        Layout.preferredHeight: 38
                        onActivated: bridge.startPreviewDownload()
                    }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: window.showingForgePreview ?
                          (bridge.forgePreview.phase === "complete" ? "Preview" : "…") :
                          Math.round(window.selectedForgeRun.progress || 0) + "%"
                    color: theme.selection
                    font.pixelSize: window.compactHeight ? 28 : 34
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: theme.border
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: window.compactHeight ? 70 : 185
                spacing: window.compactHeight ? 8 : 24
                ColumnLayout {
                    id: forgeLivePane
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 7
                    property bool technical: false
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "LIVE ACTIVITY"; color: theme.muted; font.pixelSize: 12; font.bold: true; Layout.fillWidth: true }
                        StoneButton {
                            label: forgeLivePane.technical ? "Friendly" : "Technical details"
                            accessibilityLabel: forgeLivePane.technical ? "Show friendly progress" : "Show technical details"
                            size: "inline"
                            Layout.preferredWidth: forgeLivePane.technical ? 90 : 136
                            onActivated: {
                                forgeLivePane.technical = !forgeLivePane.technical
                                if (forgeLivePane.technical) bridge.openTechnicalDetails()
                            }
                        }
                    }
                    Text {
                        visible: bridge.batchSummary !== "No URL list loaded"
                        text: bridge.batchSummary
                        color: theme.muted
                        font.pixelSize: 14
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    ScrollView {
                        id: forgeActivityViewport
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        TextArea {
                            objectName: "forgeActivityText"
                            readOnly: true
                            selectByMouse: true
                            text: window.showingForgePreview ?
                                  "Metadata only — no media is being downloaded" :
                                  forgeLivePane.technical ? bridge.forgeActivity.technical : bridge.forgeActivity.friendly
                            color: theme.muted
                            font.pixelSize: 14
                            font.family: forgeLivePane.technical ? monoFontFamily : buttonFontFamily
                            wrapMode: TextArea.Wrap
                            background: Item {}
                            leftPadding: 0
                            rightPadding: 8
                            topPadding: 0
                            bottomPadding: 0
                        }
                    }
                    RowLayout {
                        visible: bridge.running && !window.compactHeight
                        spacing: 8
                        StoneButton { label: "Cancel"; Layout.preferredWidth: 82; Layout.preferredHeight: 36; onActivated: bridge.cancel() }
                        StoneButton { label: "Skip item"; Layout.preferredWidth: 105; Layout.preferredHeight: 36; onActivated: bridge.skipItem() }
                        StoneButton { label: "Skip source"; Layout.preferredWidth: 119; Layout.preferredHeight: 36; onActivated: bridge.skipSource() }
                    }
                    StoneButton {
                        visible: bridge.running && window.compactHeight
                        label: "Run actions"
                        size: "inline"
                        Layout.preferredWidth: 110
                        onActivated: forgeRunDeck.openActiveActions()
                    }
                    StoneButton {
                        visible: bridge.batchSummary !== "No URL list loaded"
                        label: "Clear URL list"
                        Layout.preferredWidth: 116
                        Layout.preferredHeight: 34
                        onActivated: bridge.clearBatchList()
                    }
                }
                ColumnLayout {
                    visible: !window.compactHeight
                    Layout.preferredWidth: Math.min(315, window.width * 0.28)
                    Layout.fillHeight: true
                    spacing: 11
                    Text {
                        text: window.showingForgePreview ?
                              "Preview: " + window.forgeDisplayType + " · metadata only" :
                              "Output: " + window.forgeDisplayType + " · " + bridge.exportModeLabel
                        color: theme.muted
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text { text: "Format             " + window.forgeDisplayType; color: theme.muted; font.pixelSize: 14 }
                    Text {
                        text: "Video               " + (window.showingForgePreview ? "Not downloaded" : window.outputFormat === "MP4" ? "H.264" : "None")
                        color: theme.muted
                        font.pixelSize: 14
                    }
                    Text {
                        text: "Audio               " + (window.showingForgePreview ? "Not downloaded" : window.outputFormat === "MP3" ? "MP3" :
                              window.outputFormat === "Original audio" ? "Source" :
                              bridge.exportMode === "Manual Override" ? bridge.manualValues.manual_audio_codec : "AAC")
                        color: theme.muted
                        font.pixelSize: 14
                    }
                    Text { text: window.showingForgePreview ? "Output mode     Preview only" : "Output mode     " + bridge.exportModeLabel; color: theme.muted; font.pixelSize: 14 }
                    Item { Layout.fillHeight: true }
                }
            }

            Item { Layout.fillHeight: true }

            RunDeck {
                id: forgeRunDeck
                objectName: "forgeRunDeck"
                appBridge: bridge
                compact: window.compactHeight
                Layout.fillWidth: true
                Layout.preferredHeight: window.compactHeight ? 115 : 139
                onOpenSaved: function(owner) {
                    if (bridge.openLibraryDetails(owner)) bridge.select("Library")
                }
                onRemoveSaved: function(owner) {
                    if (bridge.prepareLibraryRemoval(owner)) libraryRemovalPopup.open()
                }
            }
        }

        LibraryScene {
            visible: bridge.selection === "Library"
            Layout.fillWidth: true
            Layout.fillHeight: true
            appBridge: bridge
            onAnnotationRequested: function(index) {
                if (bridge.openAnnotation(index)) annotationPopup.open()
            }
            onAnnotationOwnerRequested: function(owner) {
                if (bridge.openAnnotationOwner(owner)) annotationPopup.open()
            }
            onActionsRequested: function(owner) {
                window.selectedSavedOwner = owner
                libraryItemPopup.open()
            }
            onCollectionRequested: {
                collectionPopup.selectionPreset = []
                collectionPopup.open()
            }
            onSelectionActionRequested: function(action, owners) {
                if (!owners.length) return
                if (action === "collection") {
                    var annotationOwners = bridge.collectionOwnersForArchiveSelection(owners)
                    if (annotationOwners.length) {
                        collectionPopup.selectionPreset = annotationOwners
                        collectionPopup.open()
                    }
                } else if (action === "move") {
                    window.pendingFileOwners = owners.slice()
                    libraryMoveFolderDialog.open()
                } else if (action === "delete") {
                    if (bridge.startFileActions("delete", owners, Qt.url("")))
                        fileActionPopup.open()
                }
            }
            onCategoryRequested: categoryPopup.open()
            onImportRequested: libraryImportDialog.open()
        }
        WatchScene {
            objectName: "watchBrowseScene"
            visible: bridge.selection === "Watch" && bridge.playbackUrl.toString().length === 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            appBridge: bridge
        }
        PlayerScene {
            id: playerScene
            objectName: "watchPlayerScene"
            visible: bridge.selection === "Watch" && bridge.playbackUrl.toString().length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            appBridge: bridge
            player: window.mediaPlayer
            volume: window.playerVolume
            onCloseRequested: {
                playerScene.presentationMode = "embedded"
                if (window.mediaPlayer) window.mediaPlayer.stop()
                bridge.closePlayback()
            }
            onVolumeRequested: function(value) { window.playerVolume = value }
            onEditDetailsRequested: function(owner) {
                if (bridge.openAnnotationOwner(owner)) annotationPopup.open()
            }
        }
        ActivityScene {
            visible: bridge.selection === "Activity"
            Layout.fillWidth: true
            Layout.fillHeight: true
            appBridge: bridge
        }
    }

    Popup {
        id: missingMediaPopup
        objectName: "missingMediaPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(620, window.width - 30)
        height: 280
        padding: 18
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent; spacing: 12
            Text { text: bridge.missingMedia.heading || ""; color: theme.text; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Text { text: bridge.missingMedia.message || ""; color: theme.muted; font.pixelSize: 14; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Text { text: bridge.missingMedia.detail || ""; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideMiddle }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    label: "Find this file…"; emphasized: true
                    Layout.preferredWidth: 160; Layout.preferredHeight: 40
                    onActivated: {
                        window.pendingRelinkOwner = bridge.missingMedia.owner
                        relinkFileDialog.open()
                    }
                }
                StoneButton {
                    visible: bridge.missingMedia.primaryAction === "redownload" || bridge.missingMedia.primaryAction === "open_forge"
                    label: bridge.missingMedia.primaryLabel || "Review in Forge"
                    Layout.preferredWidth: Math.min(250, implicitWidth + 12)
                    Layout.preferredHeight: 40
                    onActivated: {
                        window.missingAction = bridge.missingMedia.primaryAction
                        if (bridge.missingMedia.requiresFolder === "yes") {
                            missingFolderDialog.open()
                        } else {
                            var accepted = window.missingAction === "redownload"
                                ? bridge.redownloadMissingTo()
                                : bridge.openMissingInForge()
                            if (accepted) missingMediaPopup.close()
                        }
                    }
                }
                Item { Layout.fillWidth: true }
                StoneButton { label: "Done"; Layout.preferredWidth: 84; Layout.preferredHeight: 40; onActivated: missingMediaPopup.close() }
            }
        }
    }
    Popup {
        id: relinkPopup
        objectName: "relinkPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(560, window.width - 30)
        height: 290
        padding: 18
        modal: true
        closePolicy: bridge.relinkInfo.phase === "working" ? Popup.NoAutoClose : Popup.CloseOnEscape
        onClosed: {
            if (bridge.relinkInfo.phase === "checking" || bridge.relinkInfo.phase === "preview") bridge.cancelRelink()
        }
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent; spacing: 12
            Text { text: bridge.relinkInfo.mode === "folder" ? "Review saved folder locations" : "Update saved file location"; color: theme.text; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
            Text { text: bridge.relinkInfo.destination; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideMiddle }
            Text { visible: bridge.relinkInfo.mode === "folder"; text: bridge.relinkInfo.readyCount + " of " + bridge.relinkInfo.selectedCount + " selected files verified"; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true }
            Text { text: bridge.relinkInfo.status; color: theme.text; font.pixelSize: 14; Layout.fillWidth: true; wrapMode: Text.WordWrap }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    visible: bridge.relinkInfo.eligible
                    label: bridge.relinkInfo.readyCount > 1 ? "Update " + bridge.relinkInfo.readyCount + " locations" : "Update location"; emphasized: true
                    Layout.preferredWidth: 170; Layout.preferredHeight: 40
                    onActivated: bridge.acceptRelink()
                }
                Item { Layout.fillWidth: true }
                StoneButton {
                    label: bridge.relinkInfo.phase === "working" ? "Stop pending update" : "Done"
                    Layout.preferredWidth: bridge.relinkInfo.phase === "working" ? 170 : 84
                    Layout.preferredHeight: 40
                    onActivated: {
                        if (bridge.relinkInfo.phase === "working") bridge.cancelRelink()
                        else relinkPopup.close()
                    }
                }
            }
        }
    }
    Popup {
        id: libraryItemPopup
        objectName: "librarySavedActionsPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: 260
        height: 418
        padding: 14
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            StoneButton {
                label: "Open folder"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: { bridge.openLibraryFolder(window.selectedSavedOwner); libraryItemPopup.close() }
            }
            StoneButton {
                label: "Copy media path"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: { bridge.copyLibraryPath(window.selectedSavedOwner); libraryItemPopup.close() }
            }
            StoneButton {
                label: "Find this file…"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: {
                    window.pendingRelinkOwner = window.selectedSavedOwner
                    libraryItemPopup.close()
                    relinkFileDialog.open()
                }
            }
            StoneButton {
                label: "Edit notes, tags & category"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: {
                    if (bridge.openAnnotationOwner(window.selectedSavedOwner)) {
                        libraryItemPopup.close()
                        annotationPopup.open()
                    }
                }
            }
            StoneButton {
                label: "Remove Library card"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: {
                    if (bridge.prepareLibraryRemoval(window.selectedSavedOwner)) {
                        libraryItemPopup.close()
                        libraryRemovalPopup.open()
                    }
                }
            }
            StoneButton {
                label: "Move media to…"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: {
                    window.pendingFileOwners = [window.selectedSavedOwner]
                    libraryItemPopup.close()
                    libraryMoveFolderDialog.open()
                }
            }
            StoneButton {
                label: "Move media to Trash"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: {
                    libraryItemPopup.close()
                    if (bridge.startFileAction("delete", window.selectedSavedOwner, Qt.url(""))) {
                        fileActionPopup.open()
                    }
                }
            }
        }
    }
    Popup {
        id: fileActionPopup
        objectName: "libraryFileActionPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(490, window.width - 40)
        height: 250
        padding: 18
        modal: true
        closePolicy: bridge.fileActionBusy ? Popup.NoAutoClose : Popup.CloseOnEscape
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text {
                text: bridge.fileActionRecovery ? "Review interrupted file change" :
                    bridge.fileActionName === "move" ? "Move saved media" : "Saved media files"
                color: theme.text
                font.pixelSize: 21
                font.bold: true
            }
            Text {
                text: bridge.fileActionStatus
                color: theme.muted
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    visible: bridge.fileActionEligible
                    label: bridge.fileActionName === "move" ? "Move verified media" : "Move to Trash"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.confirmFileAction()
                }
                StoneButton {
                    visible: bridge.fileActionRecovery && bridge.fileActionCanFinish
                    label: "Finish move"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.recoverFileAction(true)
                }
                StoneButton {
                    visible: bridge.fileActionRecovery
                    label: "Keep files as is"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.recoverFileAction(false)
                }
                Item { Layout.fillWidth: true }
                StoneButton {
                    label: "Close"
                    enabled: !bridge.fileActionBusy
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 40
                    onActivated: fileActionPopup.close()
                }
            }
        }
    }
    Popup {
        id: libraryRemovalPopup
        objectName: "libraryRemovalConfirmation"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: 380
        height: 174
        padding: 16
        modal: true
        closePolicy: Popup.CloseOnEscape
        onClosed: bridge.cancelLibraryRemoval()
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text {
                text: "Remove this Library card?"
                color: theme.text
                font.pixelSize: 19
                font.bold: true
            }
            Text {
                text: "The media file and folder stay on your computer."
                color: theme.muted
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    label: "Cancel"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onActivated: libraryRemovalPopup.close()
                }
                StoneButton {
                    label: "Remove card"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onActivated: { bridge.confirmLibraryRemoval(); libraryRemovalPopup.close() }
                }
            }
        }
    }
    Popup {
        id: collectionPopup
        objectName: "libraryCollectionPopup"
        property var selectionPreset: []
        property var selectedOwners: []
        onOpened: {
            selectedOwners = selectionPreset.slice()
            collectionName.text = ""
        }
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(540, window.width - 40)
        height: Math.min(480, window.height - 40)
        padding: 20
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text { text: "Create a collection"; color: theme.text; font.pixelSize: 23; font.bold: true }
            Text {
                text: "Choose a name, then click the media you want to include."
                color: theme.muted
                font.pixelSize: 14
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            StoneField {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                TextField {
                    id: collectionName
                    anchors.fill: parent
                    anchors.margins: 8
                    placeholderText: "Type your collection name"
                    color: theme.text
                    background: Item {}
                }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                Column {
                    width: parent.width
                    spacing: 5
                    Repeater {
                        model: bridge.collectionCandidates
                        StoneButton {
                            required property var modelData
                            width: parent.width
                            height: 36
                            label: modelData.title
                            selected: collectionPopup.selectedOwners.indexOf(modelData.owner) >= 0
                            onActivated: {
                                var next = collectionPopup.selectedOwners.slice()
                                var index = next.indexOf(modelData.owner)
                                if (index >= 0) next.splice(index, 1)
                                else next.push(modelData.owner)
                                collectionPopup.selectedOwners = next
                            }
                        }
                    }
                }
            }
            Text { text: bridge.status; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Cancel"; Layout.preferredWidth: 95; Layout.preferredHeight: 40; onActivated: collectionPopup.close() }
                StoneButton {
                    label: "Save"
                    Layout.preferredWidth: 95
                    Layout.preferredHeight: 40
                    onActivated: {
                        if (bridge.createCollection(collectionName.text, collectionPopup.selectedOwners))
                            collectionPopup.close()
                    }
                }
            }
        }
    }
    Popup {
        id: categoryPopup
        objectName: "libraryCategoryPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: 285
        height: Math.min(370, bridge.libraryCategories.length * 43 + 12)
        padding: 6
        background: StoneField {}
        ListView {
            anchors.fill: parent
            clip: true
            spacing: 3
            model: bridge.libraryCategories
            delegate: StoneButton {
                required property string modelData
                width: ListView.view.width
                height: 40
                label: modelData
                selected: bridge.libraryCategory === modelData
                onActivated: { bridge.setLibraryCategory(modelData); categoryPopup.close() }
            }
        }
    }
    Popup {
        id: annotationPopup
        objectName: "libraryAnnotationPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(570, window.width - 40)
        height: 450
        padding: 18
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 9
            Text { text: "Organize Library item"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text { text: "Your notes, tags, and category are saved privately."; color: theme.muted; font.pixelSize: 14 }
            Text { text: "Category"; color: theme.muted; font.pixelSize: 13 }
            StoneField {
                Layout.fillWidth: true; Layout.preferredHeight: 40
                TextField {
                    id: categoryInput
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                    padding: 0; verticalAlignment: TextInput.AlignVCenter
                    text: bridge.annotationValues.category
                    placeholderText: "Optional category"
                    color: theme.text; placeholderTextColor: theme.muted
                    font.pixelSize: 15; background: Item {}
                }
            }
            Text { text: "Tags (comma separated)"; color: theme.muted; font.pixelSize: 13 }
            StoneField {
                Layout.fillWidth: true; Layout.preferredHeight: 40
                TextField {
                    id: tagsInput
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                    padding: 0; verticalAlignment: TextInput.AlignVCenter
                    text: bridge.annotationValues.tags
                    placeholderText: "Optional tags"
                    color: theme.text; placeholderTextColor: theme.muted
                    font.pixelSize: 15; background: Item {}
                }
            }
            Text { text: "Private note"; color: theme.muted; font.pixelSize: 13 }
            StoneField {
                Layout.fillWidth: true; Layout.fillHeight: true
                TextArea {
                    id: noteInput
                    anchors.fill: parent; anchors.margins: 12
                    padding: 0; wrapMode: TextEdit.Wrap
                    text: bridge.annotationValues.note
                    placeholderText: "Add a note for yourself"
                    color: theme.text; placeholderTextColor: theme.muted
                    font.pixelSize: 15; background: Item {}
                }
            }
            Text { text: bridge.status; color: theme.muted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Cancel"; Layout.preferredWidth: 82; Layout.preferredHeight: 40; onActivated: annotationPopup.close() }
                StoneButton {
                    label: "Save"
                    emphasized: true
                    Layout.preferredWidth: 82; Layout.preferredHeight: 40
                    onActivated: { if (bridge.saveAnnotation(noteInput.text, tagsInput.text, categoryInput.text)) annotationPopup.close() }
                }
            }
        }
    }
    Popup {
        id: mp3OptionsPopup
        objectName: "mp3OptionsPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(560, window.width - 40)
        height: 420
        padding: 18
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 9
            Text { text: "MP3 output settings"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Repeater {
                model: [
                    { key: "mp3_quality", title: "Quality", choices: bridge.mp3QualityOptions },
                    { key: "mp3_sample_rate", title: "Sample rate", choices: bridge.mp3SampleRateOptions },
                    { key: "mp3_channels", title: "Channels", choices: bridge.mp3ChannelOptions },
                    { key: "mp3_cover_art_mode", title: "Cover art", choices: bridge.mp3CoverOptions }
                ]
                RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 47
                    Text { text: modelData.title; color: theme.muted; font.pixelSize: 14; Layout.preferredWidth: 95 }
                    StoneButton {
                        label: bridge.mp3Values[modelData.key] + "  ▾"
                        Layout.fillWidth: true; Layout.preferredHeight: 39
                        onActivated: {
                            var choices = modelData.choices
                            bridge.setMp3Value(modelData.key, choices[(choices.indexOf(bridge.mp3Values[modelData.key]) + 1) % choices.length])
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true; Layout.preferredHeight: 45
                Text { text: "Embed metadata"; color: theme.muted; font.pixelSize: 14; Layout.fillWidth: true }
                StoneButton { label: bridge.mp3Values.mp3_embed_metadata ? "On" : "Off"; selected: bridge.mp3Values.mp3_embed_metadata; Layout.preferredWidth: 74; Layout.preferredHeight: 38; onActivated: bridge.setMp3Metadata(!bridge.mp3Values.mp3_embed_metadata) }
            }
            RowLayout {
                visible: bridge.mp3Values.mp3_cover_art_mode === "Custom art"
                Layout.fillWidth: true
                Text { text: bridge.mp3CoverName; color: theme.muted; font.pixelSize: 14; elide: Text.ElideMiddle; Layout.fillWidth: true }
                StoneButton { label: "Choose image"; Layout.preferredWidth: 130; Layout.preferredHeight: 38; onActivated: mp3CoverDialog.open() }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Done"; Layout.preferredWidth: 84; Layout.preferredHeight: 40; onActivated: mp3OptionsPopup.close() }
            }
        }
    }
    Popup {
        id: settingsPopup
        objectName: "downloadSettingsPopup"
        function observeVisiblePro() {
            if (!opened || !proButton.visible) return
            const point = proButton.mapToItem(contentItem, 0, 0)
            if (point.x >= 0 && point.y >= 0 &&
                point.x + proButton.width <= contentItem.width &&
                point.y + proButton.height <= contentItem.height)
                bridge.recordCloudCtaSeen()
        }
        onOpened: Qt.callLater(observeVisiblePro)
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(820, window.width - 40)
        height: Math.min(752, window.height - 24)
        padding: 18
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 7
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Forge settings"; color: theme.text; font.pixelSize: 21; font.bold: true; Layout.fillWidth: true }
                StoneButton {
                    id: proButton
                    label: "VODForge PRO"
                    accessibilityLabel: "VODForge PRO"
                    Layout.preferredWidth: 150
                    Layout.preferredHeight: 40
                    onActivated: bridge.openCloudEarlyAccess()
                }
            }
            Text { text: "Every option is available here; the main workspace stays focused."; color: theme.muted; font.pixelSize: 14 }
            ScrollView {
                id: settingsBody
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    width: settingsBody.availableWidth
                    spacing: 16
                    GridLayout {
                        objectName: "settingsColumns"
                        Layout.fillWidth: true
                        columns: settingsBody.availableWidth >= 760 ? 2 : 1
                        columnSpacing: 16
                        rowSpacing: 18
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 360
                            spacing: 12
                    Text { text: "SAVE LOCATION"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        Layout.fillWidth: true
                        StoneField {
                            Layout.fillWidth: true; Layout.preferredHeight: 42
                            Text { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; verticalAlignment: Text.AlignVCenter; text: bridge.outputPath; color: theme.text; elide: Text.ElideMiddle; font.pixelSize: 14 }
                        }
                        StoneButton { label: "Browse"; Layout.preferredWidth: 95; Layout.preferredHeight: 40; onActivated: outputFolderDialog.open() }
                    }
                    Text { text: "BATCH AND PLAYLISTS"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        Layout.fillWidth: true
                        StoneButton { label: "Load URL list"; Layout.preferredWidth: 154; Layout.preferredHeight: 40; onActivated: urlListDialog.open() }
                        Text { text: bridge.batchSummary; color: theme.muted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    RowLayout {
                        Layout.fillWidth: true; Layout.preferredHeight: 39
                        Text { text: "Ignore playlists"; color: theme.text; font.pixelSize: 14; Layout.fillWidth: true }
                        StoneButton {
                            label: bridge.downloadOptions.single_video_only ? "On" : "Off"
                            selected: bridge.downloadOptions.single_video_only
                            Layout.preferredWidth: 74; Layout.preferredHeight: 36
                            onActivated: bridge.setDownloadOption("single_video_only", !bridge.downloadOptions.single_video_only)
                        }
                    }
                    Text { text: "YOUTUBE ACCESS"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    StoneButton { label: "YouTube access: " + bridge.cookieSource; Layout.fillWidth: true; Layout.preferredHeight: 40; onActivated: { settingsPopup.close(); accessPopup.open() } }
                    Text { text: "METADATA"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    Text { text: "Extra tags (comma-separated)"; color: theme.muted; font.pixelSize: 13 }
                    StoneField {
                        Layout.fillWidth: true; Layout.preferredHeight: 42
                        TextField {
                            id: extraTagsInput
                            objectName: "extraTagsInput"
                            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                            padding: 0; verticalAlignment: TextInput.AlignVCenter
                            color: theme.text; font.pixelSize: 14; background: Item {}
                            text: bridge.extraTags
                            onEditingFinished: {
                                if (!bridge.setExtraTags(text)) text = bridge.extraTags
                            }
                        }
                    }
                    Text { text: "Tags are added to embedded metadata and the compact metadata file when enabled."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 360
                            spacing: 12
                    Text { visible: window.outputFormat === "MP4"; text: "MP4 VIDEO"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        visible: window.outputFormat === "MP4"
                        Layout.fillWidth: true
                        StoneButton { label: "Quality: " + bridge.quality; Layout.fillWidth: true; Layout.preferredHeight: 40; onActivated: optionsMenu.open() }
                        StoneButton { label: "Output mode: " + bridge.exportModeLabel; Layout.fillWidth: true; Layout.preferredHeight: 40; onActivated: optionsMenu.open() }
                    }
                    ManualMp4Settings {
                        objectName: "settingsManualMp4"
                        visible: window.outputFormat === "MP4" && bridge.exportMode === "Manual Override"
                        Layout.fillWidth: true
                        backend: bridge
                        colors: theme
                    }
                    Text { visible: window.outputFormat === "MP4"; text: "MP4 OUTPUT FILES"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    Repeater {
                model: [
                    { key: "use_nvenc", label: "Use NVIDIA encoder for MP4" },
                    { key: "embed_thumbnail", label: "Embed thumbnail in MP4" },
                    { key: "write_thumbnail", label: "Save thumbnail beside MP4" },
                    { key: "embed_metadata", label: "Embed metadata in MP4" },
                    { key: "write_info_json", label: "Save info JSON beside MP4" }
                ]
                RowLayout {
                    required property var modelData
                    visible: window.outputFormat === "MP4"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    Text { text: modelData.label; color: theme.text; font.pixelSize: 15; Layout.fillWidth: true }
                    StoneButton {
                        label: bridge.downloadOptions[modelData.key] ? "On" : "Off"
                        selected: bridge.downloadOptions[modelData.key]
                        Layout.preferredWidth: 74
                        Layout.preferredHeight: 36
                        onActivated: bridge.setDownloadOption(modelData.key, !bridge.downloadOptions[modelData.key])
                    }
                }
                    }
                    Text { visible: window.outputFormat === "MP3"; text: "MP3 AUDIO"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    Repeater {
                        model: [
                            { key: "mp3_quality", title: "Encoding quality", choices: bridge.mp3QualityOptions },
                            { key: "mp3_sample_rate", title: "Sample rate", choices: bridge.mp3SampleRateOptions },
                            { key: "mp3_channels", title: "Channels", choices: bridge.mp3ChannelOptions },
                            { key: "mp3_cover_art_mode", title: "Cover art", choices: bridge.mp3CoverOptions }
                        ]
                        RowLayout {
                            required property var modelData
                            visible: window.outputFormat === "MP3"
                            Layout.fillWidth: true; Layout.preferredHeight: 43
                            Text { text: modelData.title; color: theme.muted; font.pixelSize: 13; Layout.preferredWidth: 118 }
                            StoneButton {
                                label: bridge.mp3Values[modelData.key] + "  ▾"
                                Layout.fillWidth: true; Layout.preferredHeight: 38
                                onActivated: {
                                    var choices = modelData.choices
                                    bridge.setMp3Value(modelData.key, choices[(choices.indexOf(bridge.mp3Values[modelData.key]) + 1) % choices.length])
                                }
                            }
                        }
                    }
                    RowLayout {
                        visible: window.outputFormat === "MP3"
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        Text { text: "Embed title, artist, and tags"; color: theme.text; font.pixelSize: 13; Layout.fillWidth: true }
                        StoneButton { label: bridge.mp3Values.mp3_embed_metadata ? "On" : "Off"; selected: bridge.mp3Values.mp3_embed_metadata; Layout.preferredWidth: 74; Layout.preferredHeight: 36; onActivated: bridge.setMp3Metadata(!bridge.mp3Values.mp3_embed_metadata) }
                    }
                    RowLayout {
                        visible: window.outputFormat === "MP3" && bridge.mp3Values.mp3_cover_art_mode === "Custom art"
                        Layout.fillWidth: true
                        Text { text: bridge.mp3CoverName; color: theme.muted; font.pixelSize: 13; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        StoneButton { label: "Replace image"; Layout.preferredWidth: 130; Layout.preferredHeight: 38; onActivated: mp3CoverDialog.open() }
                    }
                    Text {
                        visible: window.outputFormat === "Original audio"
                        text: "ORIGINAL AUDIO"
                        color: theme.muted; font.pixelSize: 13; font.bold: true
                    }
                    Text {
                        visible: window.outputFormat === "Original audio"
                        text: "Keep the source. Skip the extra compression. Saves the best available Opus or AAC stream without re-encoding."
                        color: theme.text; font.pixelSize: 15
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                    Text {
                        visible: window.outputFormat === "Original audio"
                        text: "Opus saves as .opus. AAC saves as .m4a. No bitrate or conversion settings needed."
                        color: theme.muted; font.pixelSize: 13
                        wrapMode: Text.WordWrap; Layout.fillWidth: true
                    }
                        }
                    }
                    Text { text: "APPEARANCE"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Theme"; color: theme.muted; font.pixelSize: 13 }
                        StoneButton {
                            label: bridge.appearanceTheme + "  ▾"
                            Layout.fillWidth: true; Layout.preferredHeight: 40
                            onActivated: appearanceThemeMenu.open()
                        }
                        Text { text: "Custom accent"; color: theme.muted; font.pixelSize: 13 }
                        StoneField {
                            Layout.preferredWidth: 146; Layout.preferredHeight: 40
                            TextField {
                                id: accentInput
                                anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                                padding: 0; verticalAlignment: TextInput.AlignVCenter
                                color: theme.text; font.pixelSize: 14; background: Item {}
                                text: bridge.customAccent
                                onEditingFinished: {
                                    if (!bridge.setAppearance(bridge.appearanceTheme, text)) text = bridge.customAccent
                                }
                            }
                        }
                        StoneButton { label: "Choose"; Layout.preferredWidth: 90; Layout.preferredHeight: 40; onActivated: accentColorDialog.open() }
                    }
                    Text { text: "Choose Custom accent to use a #RRGGBB color. Appearance updates immediately."; color: theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    Text { text: "PRIVACY"; color: theme.muted; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                visible: bridge.analyticsAvailable
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? 40 : 0
                Text { text: "Share anonymous usage analytics"; color: theme.text; font.pixelSize: 15; Layout.fillWidth: true }
                StoneButton {
                    label: bridge.analyticsAllowed ? "On" : "Off"
                    selected: bridge.analyticsAllowed
                    Layout.preferredWidth: 74
                    Layout.preferredHeight: 36
                    onActivated: bridge.chooseAnalytics(!bridge.analyticsAllowed)
                }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    label: "Preview metadata"
                    Layout.preferredWidth: 170
                    Layout.preferredHeight: 40
                    onActivated: {
                        if (bridge.previewMetadata(urlInput.text, window.outputFormat)) settingsPopup.close()
                    }
                }
                StoneButton { label: "Help & feedback"; Layout.preferredWidth: 160; Layout.preferredHeight: 40; onActivated: { settingsPopup.close(); bridge.openSupport("feedback") } }
                StoneButton { label: "Check for updates"; Layout.preferredWidth: 165; Layout.preferredHeight: 40; onActivated: { settingsPopup.close(); updatePopup.open(); bridge.checkForUpdates() } }
                Item { Layout.fillWidth: true }
                StoneButton {
                    label: "Done"; Layout.preferredWidth: 86; Layout.preferredHeight: 40
                    onActivated: { if (bridge.setExtraTags(extraTagsInput.text)) settingsPopup.close() }
                }
            }
        }
    }
    Popup {
        id: appearanceThemeMenu
        x: Math.max(0, settingsPopup.x + 130)
        y: Math.max(0, settingsPopup.y + settingsPopup.height - 270)
        width: 230
        height: 260
        padding: 4
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 2
            Repeater {
                model: bridge.appearanceThemes
                StoneButton {
                    required property string modelData
                    width: 222; height: 40
                    label: modelData
                    selected: bridge.appearanceTheme === modelData
                    onActivated: {
                        bridge.setAppearance(modelData, bridge.customAccent)
                        appearanceThemeMenu.close()
                    }
                }
            }
        }
    }
    Popup {
        id: updatePopup
        objectName: "updatePopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(480, window.width - 40)
        height: 265
        padding: 18
        modal: true
        closePolicy: bridge.updateBusy ? Popup.NoAutoClose : Popup.CloseOnEscape
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text { text: "VODForge updates"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text {
                text: bridge.updateStatus
                color: theme.muted
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    label: "Check again"
                    enabled: !bridge.updateBusy
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.checkForUpdates()
                }
                StoneButton {
                    visible: bridge.updateAvailable && !bridge.updateReady && !bridge.updateRecovery
                    label: "Download update"
                    enabled: !bridge.updateBusy
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.downloadUpdate()
                }
                StoneButton {
                    visible: bridge.updateReady
                    label: "Install update"
                    enabled: !bridge.updateBusy
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.installUpdate()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                StoneButton {
                    visible: bridge.updateRecovery
                    label: "Repair VODForge"
                    enabled: !bridge.updateBusy
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.repairUpdate()
                }
                StoneButton {
                    visible: bridge.updateRecovery || bridge.updateManualAvailable
                    label: "Download page"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 40
                    onActivated: bridge.openDownloadPage()
                }
                Item { Layout.fillWidth: true }
                StoneButton {
                    label: "Close"
                    enabled: !bridge.updateBusy
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 40
                    onActivated: updatePopup.close()
                }
            }
        }
    }
    Popup {
        id: accessPopup
        objectName: "youtubeAccessPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(560, window.width - 40)
        height: 410
        padding: 18
        modal: true
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Text { text: "YouTube access"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text {
                text: "Public needs no account. For restricted videos, choose a signed-in browser or a cookies.txt file."
                color: theme.muted; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Repeater {
                    model: ["Public", "Browser", "cookies.txt"]
                    StoneButton {
                        required property string modelData
                        label: modelData
                        selected: bridge.cookieSource === modelData
                        Layout.fillWidth: true; Layout.preferredHeight: 39
                        onActivated: bridge.setCookieSource(modelData)
                    }
                }
            }
            Flow {
                visible: bridge.cookieSource === "Browser"
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? 125 : 0
                spacing: 6
                Repeater {
                    model: bridge.cookieBrowserOptions
                    StoneButton {
                        required property string modelData
                        label: modelData
                        selected: bridge.cookieBrowser === modelData
                        width: 115; height: 37
                        onActivated: bridge.setCookieBrowser(modelData)
                    }
                }
            }
            RowLayout {
                visible: bridge.cookieSource === "cookies.txt"
                Layout.fillWidth: true
                Text { text: bridge.cookieFileName; color: theme.muted; font.pixelSize: 14; elide: Text.ElideMiddle; Layout.fillWidth: true }
                StoneButton { label: "Choose file"; Layout.preferredWidth: 108; Layout.preferredHeight: 38; onActivated: cookieFileDialog.open() }
            }
            Text {
                text: bridge.cookieSource === "Browser" ? "VODForge reads this browser’s sign-in store for the run. On Windows, use Firefox or cookies.txt for Chromium browsers." :
                      bridge.cookieSource === "cookies.txt" ? "The selected file is used for this session. Its contents are not stored in settings." :
                      "No account information is used."
                color: theme.muted; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Done"; Layout.preferredWidth: 84; Layout.preferredHeight: 40; onActivated: accessPopup.close() }
            }
        }
    }
    Popup {
        id: localConversionPopup
        objectName: "localConversionPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(500, window.width - 40)
        height: 310
        padding: 18
        modal: true
        closePolicy: bridge.localRunning ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: StoneField {}
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Text { text: "Create video from local audio"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text { text: "Choose an MP3 and a still image. The MP4 saves to your output folder."; color: theme.muted; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                StoneField {
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    Text { anchors.fill: parent; anchors.margins: 12; text: bridge.localAudio || "Choose MP3 audio"; color: theme.text; font.pixelSize: 14; elide: Text.ElideMiddle; verticalAlignment: Text.AlignVCenter }
                }
                StoneButton { label: "Browse"; Layout.preferredWidth: 85; Layout.preferredHeight: 40; enabled: !bridge.localRunning; onActivated: localAudioDialog.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                StoneField {
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    Text { anchors.fill: parent; anchors.margins: 12; text: bridge.localImage || "Choose still image"; color: theme.text; font.pixelSize: 14; elide: Text.ElideMiddle; verticalAlignment: Text.AlignVCenter }
                }
                StoneButton { label: "Browse"; Layout.preferredWidth: 85; Layout.preferredHeight: 40; enabled: !bridge.localRunning; onActivated: localImageDialog.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Profile"; color: theme.muted; font.pixelSize: 14 }
                Item { Layout.fillWidth: true }
                StoneButton { label: bridge.localProfile + "  ▾"; Layout.preferredWidth: 295; Layout.preferredHeight: 38; enabled: !bridge.localRunning; onActivated: localProfilePopup.open() }
            }
            Text { text: bridge.localProgress || bridge.status; color: theme.muted; font.pixelSize: 14; elide: Text.ElideRight; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Close"; Layout.preferredWidth: 82; Layout.preferredHeight: 40; enabled: !bridge.localRunning; onActivated: localConversionPopup.close() }
                StoneButton { label: bridge.localRunning ? "Stop" : "Create MP4"; emphasized: !bridge.localRunning; Layout.preferredWidth: 110; Layout.preferredHeight: 40; onActivated: bridge.localRunning ? bridge.cancelLocalConversion() : bridge.startLocalConversion() }
            }
        }
    }
    Popup {
        id: localProfilePopup
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: 320
        height: 184
        padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 2
            Repeater {
                model: localVideoProfiles
                StoneButton {
                    required property string modelData
                    width: 314; height: 42
                    label: modelData
                    selected: bridge.localProfile === modelData
                    onActivated: { bridge.setLocalProfile(modelData); localProfilePopup.close() }
                }
            }
        }
    }
    Popup {
        id: formatMenu
        x: Math.max(0, window.width - window.gutter - 375)
        y: window.gutter + 112
        width: 170
        height: 150
        padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 3
            Repeater {
                model: ["MP4", "MP3", "Original audio"]
                StoneButton {
                    required property string modelData
                    width: 164
                    height: 44
                    label: modelData
                    selected: window.outputFormat === modelData
                    onActivated: {
                        bridge.setOutputFormat(modelData)
                        formatMenu.close()
                        if (modelData === "MP3") mp3OptionsPopup.open()
                    }
                }
            }
        }
    }
    Popup {
        id: optionsMenu
        objectName: "optionsMenu"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(550, window.width - 40)
        height: 350
        padding: 8
        background: StoneField {}
        Row {
            anchors.fill: parent
            spacing: 8
            Column {
                width: (parent.width - 8) / 2
                spacing: 3
                Text { text: "Output mode"; color: theme.muted; font.pixelSize: 13; height: 25 }
                Repeater {
                    model: bridge.exportModeOptions
                    StoneButton {
                        required property var modelData
                        width: parent.width; height: 40
                        label: modelData.label
                        selected: bridge.exportMode === modelData.value
                        onActivated: {
                            bridge.setExportMode(modelData.value)
                            optionsMenu.close()
                        }
                    }
                }
            }
            Column {
                width: (parent.width - 8) / 2
                spacing: 3
                Text { text: "Quality"; color: theme.muted; font.pixelSize: 13; height: 25 }
                Repeater {
                    model: qualityOptions
                    StoneButton {
                        required property string modelData
                        width: parent.width; height: 40
                        label: modelData
                        selected: bridge.quality === modelData
                        onActivated: { bridge.setQuality(modelData); optionsMenu.close() }
                    }
                }
            }
        }
    }
}
