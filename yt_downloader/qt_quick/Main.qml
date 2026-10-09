import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtMultimedia

Window {
    id: window
    RunStatusTone { id: runStatusTone }
    readonly property bool menuNavigationAllowed: !analyticsPopup.visible && !editorialPopup.visible &&
            !socialInvitationPopup.visible && !helpMenu.visible && !supportPopup.visible && !supportReasonMenu.visible &&
            !supportDiagnostics.visible && !libraryItemPopup.visible &&
            !fileActionPopup.visible && !libraryRemovalPopup.visible &&
            !collectionPopup.visible && !collectionTargetPopup.visible &&
            !annotationPopup.visible && !mp3OptionsPopup.visible && !settingsPopup.visible &&
            !updatePopup.visible && !accessPopup.visible &&
            !localConversionPopup.visible && !localProfilePopup.visible &&
            !formatMenu.visible && !optionsMenu.visible &&
            !settingsQualityMenu.visible && !settingsOutputModeMenu.visible && !translatedSubtitleMenu.visible &&
            !(outputFolderDialog && outputFolderDialog.visible) && !urlListDialog.visible
    // Native panels use the application's standard editing menu selectors.
    Loader {
        active: Qt.platform.os === "osx"
        sourceComponent: Component {
            ApplicationMenuBar {
                appWindow: window
                controller: bridge
                navigationAllowed: window.menuNavigationAllowed
                onOutputFolderRequested: window.openOutputFolderDialog()
                onUrlListRequested: urlListDialog.open()
                onSettingsRequested: settingsPopup.open()
            }
        }
    }

    visible: true
    width: 1100
    height: 740
    x: 30
    y: 30
    minimumWidth: 820
    minimumHeight: 560
    title: "VODForge"
    color: Qt.platform.os === "osx" ? "transparent" : theme.bg
    property real backgroundOpacity: 1.0
    readonly property color glassSurfaceColor: theme.bg
    readonly property real glassControlOpacity: backgroundOpacity < 1.0 ? 0.64 : 1.0
    // Qt's folder helper retains its directory after the first show. A new
    // public dialog instance applies the current destination on every opening.
    readonly property var outputFolderDialog: outputFolderDialogLoader.item
    function openOutputFolderDialog() {
        if (outputFolderDialog && outputFolderDialog.visible) return
        outputFolderDialogLoader.active = false
        outputFolderDialogLoader.active = true
        outputFolderDialog.currentFolder = bridge.outputFolderUrl
        outputFolderDialog.open()
    }
    property real playerVolume: 0.8
    readonly property bool editingText: activeFocusItem instanceof TextInput ||
                                       activeFocusItem instanceof TextEdit
    function retireHiddenSceneFocus() {
        const item = window.activeFocusItem
        // A route can hide an editor without Qt releasing its keyboard focus.
        // Retire only that hidden owner; shared visible editors/popups keep focus.
        if (item && !item.visible) {
            // Clear hidden focus scopes too: focusing the window otherwise
            // restores their remembered child after the editor is retired.
            let owner = item
            while (owner && !owner.visible) {
                owner.focus = false
                owner = owner.parent
            }
            window.contentItem.forceActiveFocus(Qt.OtherFocusReason)
        }
    }
    property string pendingRelinkOwner: ""
    property string missingAction: ""
    property string pendingRelinkFolderPath: ""
    property var mediaPlayer: playerLoader.item
    property bool miniPlayerActive: false
    property int miniPlayerCorner: 3
    function expandMiniPlayer() {
        miniPlayerActive = false
        bridge.select("Watch")
    }
    readonly property var selectedForgeRun: bridge.forgeSelection
    readonly property string selectedForgeToneStatus:
        window.showingForgePreview && bridge.forgePreview.phase === "failed" ?
            "Failed" : (window.selectedForgeRun.status || "")
    readonly property bool showingForgePreview: selectedForgeRun.kind === "preview"
    readonly property string forgeDisplayType: selectedForgeRun.type || window.outputFormat
    readonly property bool playerSurfaceBound: mediaPlayer && mediaPlayer.videoOutput === playerScene.activeVideoSurface
    property int pendingPlaybackGeneration: -1
    // The shared diagnostics owner receives only these bounded scene counts.
    // Source URLs stay inside QML and are never sent to telemetry.
    property var presentationDiagnosticSnapshot: ({})
    function refreshPresentationDiagnosticSnapshot() {
        const counts = {
            artworkExpected: 0, artworkDisplayed: 0, artworkUnavailable: 0,
            pending: 0, artworkPending: 0, missing: 0, missingRoles: [], rendered: 0,
            visible: window.visible, eligible: bridge.savedCount, matching: 0
        }
        const projection = bridge.selection === "Library"
            ? libraryBrowseScene.projection
            : bridge.selection === "Watch" ? watchBrowseScene.projection : ({})
        counts.matching = (projection.media || projection.videos || []).length
            + (projection.groups || []).length
        const repeaters = {
            libraryGroupRepeater: true, libraryMediaRepeater: true,
            libraryFolderList: true, watchGroupRepeater: true,
            watchMediaRepeater: true
        }
        function inspect(item) {
            if (!item || !item.visible) return
            const name = String(item.objectName || "")
            if (repeaters[name] && typeof item.count === "number")
                counts.rendered += item.count
            if (typeof item.source !== "undefined"
                    && typeof item.status !== "undefined"
                    && typeof item.paintedWidth !== "undefined"
                    && item.width > 0 && item.height > 0) {
                const source = String(item.source || "")
                if (source.length > 0) {
                    const role = item.presentationRole ||
                        (source.indexOf("image://vodforge/") === 0
                            ? (source.indexOf("/backdrop/") >= 0 ? "surface" : "control")
                            : source.indexOf(assetUrl) === 0 ? "surface" : "artwork")
                    if (role === "artwork") counts.artworkExpected++
                    if (item.status === Image.Ready) {
                        if (role === "artwork" && item.presentationPaintedReady !== false)
                            counts.artworkDisplayed++
                    } else if (item.status === Image.Error) {
                        counts.missing++
                        counts.missingRoles.push(role)
                        if (role === "artwork") counts.artworkUnavailable++
                    } else if (item.status === Image.Loading) {
                        counts.pending++
                        if (role === "artwork") counts.artworkPending++
                    }
                }
            }
            const children = item.children || []
            for (let index = 0; index < children.length; index++)
                inspect(children[index])
        }
        inspect(window.contentItem)
        presentationDiagnosticSnapshot = counts
    }
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
            videoOutput: window.miniPlayerActive ? miniVideoSurface : playerScene.activeVideoSurface
            function reportProgress() {
                var status = "Ready"
                if (error !== MediaPlayer.NoError) status = "Failed"
                else if (mediaStatus === MediaPlayer.EndOfMedia) status = "Ended"
                else if (playbackState === MediaPlayer.PlayingState) status = "Playing"
                else if (playbackState === MediaPlayer.PausedState) status = "Paused"
                bridge.observePlayback(position / 1000, duration / 1000, status, generation, error)
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
        function onSelectionChanged() {
            // Visibility bindings must settle before testing the outgoing owner.
            Qt.callLater(window.retireHiddenSceneFocus)
        }
        function onOperationFeedback(message) {
            operationNotice.message = message
            operationNotice.open()
            operationNoticeTimer.restart()
        }
        function onOutputFolderRecoveryRequested(message) {
            outputFolderRecoveryPopup.message = message
            outputFolderRecoveryPopup.open()
        }
        function onAnalyticsPromptRequested() { analyticsPopup.open() }
        function onSupportRequested() {
            supportPopup.reason = "Select one…"
            supportPopup.stars = 0
            supportPopup.reply = false
            supportPopup.includeDiagnostics = false
            supportPopup.includeVideoUrl = false
            supportPopup.includeOutputFolder = false
            supportMessage.text = ""
            supportEmail.text = ""
            supportName.text = ""
            supportPopup.open()
        }
        function onEditorialRequested() { editorialPopup.open() }
        function onSocialInvitationRequested() { socialInvitationPopup.open() }
        function onFileActionRequested() { fileActionPopup.open() }
        function onLibraryRemovalRequested() { libraryRemovalPopup.open() }
        function onSourceAccepted() { urlInput.text = "" }
        function onSourcePrepared(url) { urlInput.text = url }
        function onMissingMediaRequested() { missingMediaPopup.open() }
        function onFolderRelinkRequested(path) {
            window.pendingRelinkFolderPath = path
            relinkFolderDialog.open()
        }
        function onFileRelinkRequested(owner) {
            window.pendingRelinkOwner = owner
            relinkFileDialog.open()
        }
        function onPlaybackRequested(generation) {
            // Retire the old provider object before a queued item opens. Any
            // late signal carries the old generation and cannot advance it.
            window.pendingPlaybackGeneration = generation
            window.miniPlayerActive = false
            playerLoader.sourceComponent = null
            playerScene.clearVideoFrames()
            miniVideoSurface.clearOutput()
            playerLoader.sourceComponent = mediaPlayerComponent
        }
        function onPlaybackUrlChanged() {
            if (bridge.playbackUrl.toString().length > 0) return
            window.miniPlayerActive = false
            window.pendingPlaybackGeneration = -1
            if (window.mediaPlayer) window.mediaPlayer.stop()
            playerLoader.sourceComponent = null
            playerScene.clearVideoFrames()
            miniVideoSurface.clearOutput()
        }
        function onPlaybackSeekRequested(position) {
            if (window.mediaPlayer) mediaPlayer.setPosition(position * 1000)
        }
    }
    EditorialPopup {
        id: editorialPopup
        parent: window.contentItem
        slides: bridge.editorialSlides
        reducedMotion: bridge.reducedMotion
        heading: bridge.editorialHeading
        finishLabel: bridge.editorialFinishLabel
        showSocialInvitation: bridge.compactWelcome
        onSocialFollowRequested: bridge.openSocialAccount()
        onAcknowledged: function(tryIt) {
            bridge.dismissEditorial(tryIt)
            if (tryIt) settingsPopup.open()
        }
    }
    StonePopup {
        id: outputDetailsPopup
        objectName: "forgeOutputDetailsPopup"
        parent: window.contentItem
        width: Math.min(440, window.width - 40)
        height: Math.min(330, window.height - 40)
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        padding: 20
        modal: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        ScrollView {
            objectName: "forgeOutputDetailsScroll"
            anchors.fill: parent
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ForgeSourceDetails {
                width: parent.availableWidth
                appBridge: bridge
                outputFormat: window.outputFormat
                displayType: window.forgeDisplayType
                preview: window.showingForgePreview
                // Pending choices refresh live; selected-run facts retain their job snapshot.
                selectedFacts: (bridge.outputFormat, bridge.exportMode, bridge.quality,
                                bridge.outputPath, bridge.downloadOptions, bridge.nvencAvailable,
                                bridge.manualValues, bridge.mp3Values, bridge.cookieSource,
                                bridge.cookieBrowser, bridge.extraTags, bridge.batchSummary,
                                bridge.forgeSelectedFacts)
            }
        }
    }
    Timer {
        interval: 700
        running: true
        repeat: true
        onTriggered: bridge.checkEditorial(
            window.active && !window.editingText && !analyticsPopup.visible && !editorialPopup.visible &&
            !socialInvitationPopup.visible && !helpMenu.visible && !supportPopup.visible && !supportReasonMenu.visible &&
            !supportDiagnostics.visible && !libraryItemPopup.visible &&
            !fileActionPopup.visible && !libraryRemovalPopup.visible &&
            !collectionPopup.visible && !collectionTargetPopup.visible &&
            !annotationPopup.visible && !mp3OptionsPopup.visible && !settingsPopup.visible &&
            !updatePopup.visible && !accessPopup.visible &&
            !localConversionPopup.visible && !localProfilePopup.visible &&
            !formatMenu.visible && !optionsMenu.visible &&
            !settingsQualityMenu.visible && !settingsOutputModeMenu.visible && !translatedSubtitleMenu.visible)
    }
    AnchoredPopup {
        id: helpMenu
        objectName: "helpMenu"
        parent: window.contentItem
        preferAbove: true
        width: 235
        height: helpMenuContent.implicitHeight + 2 * padding + 2
        padding: 3
        Column {
            id: helpMenuContent
            anchors.fill: parent
            spacing: 3
            StoneButton {
                width: parent.width; height: 46
                label: "Support"
                onActivated: { helpMenu.close(); settingsPopup.close(); bridge.openSupport("feedback") }
            }
            StoneButton {
                width: parent.width; height: 46
                label: "Write a review"
                onActivated: { helpMenu.close(); settingsPopup.close(); bridge.openSupport("review") }
            }
            StoneButton {
                objectName: "helpWhatsNew"
                width: parent.width; height: 46
                visible: bridge.whatsNewAvailable
                label: "What’s new"
                onActivated: { helpMenu.close(); settingsPopup.close(); bridge.openWhatsNew() }
            }
            StoneButton {
                width: parent.width; height: 46
                label: "Welcome tour"
                onActivated: { helpMenu.close(); settingsPopup.close(); bridge.openWelcomeTour() }
            }
        }
    }
    StonePopup {
        id: socialInvitationPopup
        objectName: "socialInvitationPopup"
        parent: window.contentItem
        width: Math.min(430, window.width - 36)
        height: socialInvitationLayout.implicitHeight + 2 * padding
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        padding: 22
        modal: true
        closePolicy: Popup.CloseOnEscape
        onClosed: bridge.dismissSocialInvitation(false)
        ColumnLayout {
            id: socialInvitationLayout
            anchors.fill: parent
            spacing: 14
            StoneButton {
                sceneIcon: "x"
                accessibilityLabel: "VODForge on X"
                quiet: true
                interactive: false
                Layout.alignment: Qt.AlignHCenter
                Layout.preferredWidth: 40
                Layout.preferredHeight: 40
            }
            Text {
                text: "Stay connected with VODForge"
                color: theme.text
                font.pixelSize: 22
                font.bold: true
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
            }
            Text {
                text: "Follow @VODForge on X for the fastest support and the latest platform updates."
                color: theme.muted
                font.pixelSize: 14
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 4
                spacing: 10
                StoneButton {
                    objectName: "socialInvitationLater"
                    label: "Not now"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onActivated: socialInvitationPopup.close()
                }
                StoneButton {
                    objectName: "socialInvitationFollow"
                    label: "Follow on X"
                    emphasized: true
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    onActivated: { bridge.dismissSocialInvitation(true); socialInvitationPopup.close() }
                }
            }
        }
    }
    StonePopup {
        id: supportPopup
        objectName: "supportPopup"
        property string reason: "Select one…"
        property int stars: 0
        property bool reply: false
        property bool includeDiagnostics: false
        property bool includeVideoUrl: false
        property bool includeOutputFolder: false
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(580, window.width - 18)
        height: Math.min(supportLayout.implicitHeight + 2 * padding, window.height - 18)
        padding: 18
        modal: true
        closePolicy: bridge.supportBusy ? Popup.NoAutoClose : Popup.CloseOnEscape
        onClosed: bridge.closeSupport()
        ColumnLayout {
            id: supportLayout
            anchors.fill: parent
            spacing: 9
            Text {
                text: bridge.supportKind === "feedback" ? "Support" : "How’s VODForge working for you?"
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
                objectName: "supportBody"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredHeight: supportFields.implicitHeight
                Layout.minimumHeight: Math.min(160, supportFields.implicitHeight)
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ColumnLayout {
                    id: supportFields
                    objectName: "supportFields"
                    width: supportBody.availableWidth
                    spacing: 8
                    StoneButton {
                        visible: bridge.supportKind === "feedback"
                        label: supportPopup.reason + "  ▾"
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onActivated: { supportReasonMenu.anchorItem = this; supportReasonMenu.toggleFrom(this) }
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
                    StoneCheckBox {
                        objectName: "supportReplyConsent"
                        visible: bridge.supportKind === "feedback"
                        text: "I’d like a reply"
                        checked: supportPopup.reply
                        Layout.preferredWidth: 190; Layout.preferredHeight: 32
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onToggled: supportPopup.reply = checked
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
                    StoneCheckBox {
                        objectName: "supportDiagnosticsConsent"
                        visible: bridge.supportKind === "feedback"
                        text: "Include recent diagnostics"
                        checked: supportPopup.includeDiagnostics
                        Layout.fillWidth: true; Layout.preferredHeight: 32
                        enabled: !!bridge.supportContext.diagnostics && !bridge.supportBusy && !bridge.supportSent
                        onToggled: supportPopup.includeDiagnostics = checked
                    }
                    Text {
                        visible: bridge.supportKind === "feedback" && !bridge.supportContext.diagnostics
                        text: "No recent failed-run diagnostics available."
                        color: theme.muted; font.pixelSize: 12
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                    }
                    StoneButton {
                        visible: bridge.supportKind === "feedback" && !!bridge.supportContext.diagnostics
                        label: "Review diagnostics"
                        size: "inline"
                        Layout.preferredWidth: 165
                        onActivated: supportDiagnostics.toggleFrom(this)
                    }
                    StoneCheckBox {
                        visible: bridge.supportKind === "feedback" && !!bridge.supportContext.videoUrl
                        text: "Include YouTube source link"
                        checked: supportPopup.includeVideoUrl
                        Layout.preferredWidth: 245; Layout.preferredHeight: 32
                        enabled: !bridge.supportBusy && !bridge.supportSent
                        onToggled: supportPopup.includeVideoUrl = checked
                    }
                    StoneCheckBox {
                        objectName: "supportOutputFolderConsent"
                        visible: bridge.supportKind === "feedback" && !!bridge.supportContext.outputFolder
                        text: "Include output folder path"
                        checked: supportPopup.includeOutputFolder
                        Layout.fillWidth: true; Layout.preferredHeight: 32
                        enabled: supportPopup.includeDiagnostics && !bridge.supportBusy && !bridge.supportSent
                        onToggled: supportPopup.includeOutputFolder = checked
                    }
                    Text {
                        visible: bridge.supportKind === "feedback" && (!!bridge.supportContext.outputFolder || !!bridge.supportContext.videoUrl)
                        text: "Source links and folder names can identify your content. Review your selected attachments before sending."
                        color: theme.muted; font.pixelSize: 12
                        Layout.fillWidth: true; wrapMode: Text.WordWrap
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
                        outputFolder: supportPopup.includeOutputFolder,
                        name: supportName.text
                    })
                }
            }
        }
    }
    AnchoredPopup {
        id: supportReasonMenu
        parent: window.contentItem
        preferAbove: true
        width: 290; height: 238; padding: 3
        scrollViewport: supportBody
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
    StonePopup {
        id: supportDiagnostics
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(580, window.width - 24)
        height: Math.min(430, window.height - 24)
        padding: 16; modal: true
        ColumnLayout {
            anchors.fill: parent
            Text { text: "Review diagnostics"; color: theme.text; font.pixelSize: 22; font.bold: true }
            ScrollView {
                id: diagnosticsBody
                Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                Text {
                    objectName: "supportAttachmentPreview"
                    text: bridge.supportAttachmentPreview(supportPopup.includeDiagnostics, supportPopup.includeVideoUrl, supportPopup.includeOutputFolder)
                    color: theme.text; font.pixelSize: 14
                    width: diagnosticsBody.availableWidth; wrapMode: Text.WrapAnywhere
                }
            }
            StoneButton { label: "Done"; Layout.alignment: Qt.AlignRight; Layout.preferredWidth: 82; onActivated: supportDiagnostics.close() }
        }
    }
    StonePopup {
        id: analyticsPopup
        objectName: "analyticsConsentPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(840, window.width - 40)
        height: analyticsContent.implicitHeight + topPadding + bottomPadding
        padding: 20
        modal: true
        closePolicy: Popup.NoAutoClose
        ColumnLayout {
            id: analyticsContent
            anchors.fill: parent
            spacing: 20
            Text { text: "Help improve VODForge"; color: theme.text; font.pixelSize: 21; font.bold: true; Layout.alignment: Qt.AlignHCenter }
            Text {
                text: bridge.analyticsDescription
                color: theme.text
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
            }
            GridLayout {
                objectName: "analyticsBenefits"
                Layout.alignment: Qt.AlignHCenter
                columns: analyticsPopup.availableWidth >= 760 ? 4 : 2
                columnSpacing: 16; rowSpacing: 20
                Repeater {
                    model: bridge.analyticsBenefits
                    delegate: ColumnLayout {
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        spacing: 9
                        SceneIcon {
                            objectName: "analyticsBenefitIcon_" + index
                            name: modelData.icon; tone: theme.accent
                            Layout.preferredWidth: 36; Layout.preferredHeight: 36
                            Layout.alignment: Qt.AlignHCenter
                        }
                        Text {
                            objectName: "analyticsBenefitLabel_" + index
                            text: modelData.label; color: theme.muted
                            font.pixelSize: 13
                            Layout.alignment: Qt.AlignHCenter
                        }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                StoneButton { label: "Privacy details"; Layout.preferredWidth: 160; Layout.preferredHeight: 38; onActivated: bridge.openPrivacy() }
                Item { Layout.fillWidth: true }
                StoneButton { label: "No thanks"; Layout.preferredWidth: 115; Layout.preferredHeight: 40; onActivated: { if (bridge.chooseAnalytics(false)) analyticsPopup.close() } }
                StoneButton { label: "Share analytics"; Layout.preferredWidth: 150; Layout.preferredHeight: 40; onActivated: { if (bridge.chooseAnalytics(true)) analyticsPopup.close() } }
            }
        }
    }
    StonePopup {
        id: outputFolderRecoveryPopup
        objectName: "outputFolderRecoveryPopup"
        property string message: ""
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(520, window.width - 30)
        height: 220
        padding: 18
        modal: true
        Text {
            anchors.top: parent.top
            width: parent.width
            height: parent.height - 58
            text: outputFolderRecoveryPopup.message
            color: theme.text
            font.pixelSize: 16
            wrapMode: Text.WordWrap
        }
        RowLayout {
            anchors.bottom: parent.bottom
            width: parent.width
            StoneButton {
                objectName: "outputFolderRecoveryChoose"
                label: "Choose folder"
                emphasized: true
                Layout.preferredWidth: 150
                Layout.preferredHeight: 40
                onActivated: {
                    outputFolderRecoveryPopup.close()
                    window.openOutputFolderDialog()
                }
            }
            Item { Layout.fillWidth: true }
            StoneButton {
                label: "Later"
                Layout.preferredWidth: 84
                Layout.preferredHeight: 40
                onActivated: outputFolderRecoveryPopup.close()
            }
        }
    }
    Loader {
        id: outputFolderDialogLoader
        sourceComponent: Component {
            FolderDialog {
                objectName: "outputFolderDialog"
                title: "Choose output folder"
                currentFolder: bridge.outputFolderUrl
                onAccepted: bridge.chooseOutputUrl(selectedFolder)
            }
        }
    }
    ComposerNotice {
        id: operationNotice
        attached: bridge.selection === "Forge"
        objectName: "operationNotice"
        parent: window.contentItem
        reducedMotion: bridge.reducedMotion
        availableWidth: Math.max(120, Math.min(440, window.width - 30))
        x: bridge.selection === "Forge"
            ? Math.max(10, Math.min(window.width - width - 10,
                forgeNoticeLayer.x + forgeComposerShell.x + (forgeComposerShell.width - width) / 2))
            : Math.max(10, (window.width - width) / 2)
        y: bridge.selection === "Forge"
            ? forgeNoticeLayer.y + forgeComposerShell.y + forgeComposerShell.height
            : window.height - height - 18
    }
    Timer { id: operationNoticeTimer; interval: 3500; onTriggered: operationNotice.close() }
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
        title: "Locate the folder containing the moved files"
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
        opacity: window.backgroundOpacity
        property string presentationRole: "surface"
        anchors.fill: parent
        source: "image://vodforge/backdrop/r" + bridge.themeRevision
        fillMode: Image.PreserveAspectCrop
        smooth: true
        cache: true
    }

    Rectangle {
        anchors.fill: parent
        visible: window.backgroundOpacity < 1.0
        color: Qt.rgba(0.12, 0.26, 0.40, 0.02)
    }

    property int gutter: width < 960 ? 12 : 20
    property bool compactHeight: height < 640
    property int rowGap: compactHeight ? 8 : 14
    readonly property string forgeDensity: width < 920 || height < 690 ? "compact" :
        width < 1080 || height < 760 ? "balanced" : "wide"
    readonly property int forgeHorizontalPad: forgeDensity === "compact" ? 20 : forgeDensity === "balanced" ? 42 : 100
    readonly property int forgeTopPad: forgeDensity === "compact" ? 18 : forgeDensity === "balanced" ? 26 : 42
    property string outputFormat: bridge.outputFormat
    property string selectedSavedOwner: ""
    property var pendingFileOwners: []

    Item {
        id: forgeNoticeLayer
        parent: window.contentItem
        x: forgeViewport.x + forgeViewport.parent.x - 8
        y: forgeViewport.y + forgeViewport.parent.y - 8
        width: forgeViewport.width + 16
        height: forgeViewport.height + 8
        clip: true
        visible: bridge.selection === "Forge"
    }
    Item {
        id: forgeComposerShell
        objectName: "forgeComposerShell"
        parent: forgeNoticeLayer
        visible: bridge.selection === "Forge"
        x: forgeCommandRow.x
        y: forgeCommandRow.y - forgeViewport.contentItem.contentY
        width: forgeCommandRow.width + 16
        height: forgeLocalRow.y + forgeLocalRow.height - forgeCommandRow.y + 16
        Canvas {
            anchors.left: parent.left
            anchors.top: parent.top
            width: parent.width
            height: parent.height + operationNotice.height
            property real shellHeight: forgeComposerShell.height
            property real reveal: operationNotice.reveal
            property real noticeWidth: operationNotice.width
            property color surfaceColor: Qt.rgba(window.glassSurfaceColor.r,
                window.glassSurfaceColor.g, window.glassSurfaceColor.b, window.glassControlOpacity)
            property color edgeColor: theme.border
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onShellHeightChanged: requestPaint()
            onRevealChanged: requestPaint()
            onNoticeWidthChanged: requestPaint()
            onSurfaceColorChanged: requestPaint()
            onEdgeColorChanged: requestPaint()
            onPaint: {
                const c = getContext("2d")
                c.clearRect(0, 0, width, height)
                const w = width - 1, h = shellHeight - 0.5, r = 16
                const drop = operationNotice.height * reveal
                const half = noticeWidth * (0.30 + 0.70 * reveal) / 2
                const left = width / 2 - half, right = width / 2 + half
                const turn = Math.min(8, drop / 2)
                c.beginPath(); c.moveTo(r, 0.5); c.lineTo(w-r, 0.5)
                c.quadraticCurveTo(w, 0.5, w, r); c.lineTo(w, h-r)
                c.quadraticCurveTo(w, h, w-r, h)
                c.lineTo(right+turn, h)
                c.quadraticCurveTo(right, h, right, h+turn)
                c.lineTo(right, h+drop-turn)
                c.quadraticCurveTo(right, h+drop, right-turn, h+drop)
                c.lineTo(left+turn, h+drop)
                c.quadraticCurveTo(left, h+drop, left, h+drop-turn)
                c.lineTo(left, h+turn)
                c.quadraticCurveTo(left, h, left-turn, h)
                c.lineTo(r, h); c.quadraticCurveTo(0.5, h, 0.5, h-r)
                c.lineTo(0.5, r); c.quadraticCurveTo(0.5, 0.5, r, 0.5)
                c.closePath(); c.fillStyle = surfaceColor; c.fill()
                c.strokeStyle = edgeColor; c.lineWidth = 1; c.stroke()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: window.gutter
        anchors.rightMargin: window.gutter
        anchors.topMargin: 5
        anchors.bottomMargin: window.width < 960 ? 10 : 14
        spacing: 2

        Item {
            id: focusHeader
            objectName: "focusHeader"
            Layout.fillWidth: true
            Layout.preferredHeight: stacked ? 100 : 44
            // Keep the compact lockup until the expanded brand and minimum
            // search field fit. A fixed 960px switch briefly wrapped this row,
            // then unwrapped it a few pixels later, shrinking Watch in between.
            readonly property bool compact: window.width < 960 || width <
                nativeHeaderInset + 150 + navWidth +
                ((bridge.selection === "Library" || bridge.selection === "Watch") ? 193 : 0) + 72
            readonly property int nativeHeaderInset: Qt.platform.os === "osx" ? 82 : 0
            readonly property int brandWidth: nativeHeaderInset + (compact ? 46 : 150)
            readonly property int searchWidth: Math.max(compact ? 124 : 185,
                Math.min(compact ? 186 : 285,
                    width - brandWidth - navWidth - 88))
            readonly property int navWidth: navigationRow.implicitWidth
            readonly property int utilityWidth:
                (bridge.selection === "Library" || bridge.selection === "Watch"
                    ? searchWidth + 8 : 0) + 64
            readonly property bool stacked: brandWidth + navWidth + utilityWidth + 8 > width

            MouseArea {
                id: headerDragArea
                objectName: "headerDragArea"
                anchors.fill: parent
                // Blank gutters and layout spacing above the divider drag too.
                anchors.leftMargin: -window.gutter
                anchors.rightMargin: -window.gutter
                anchors.bottomMargin: -2
                z: -1
                property bool awaitingSystemMove: false
                onReleased: awaitingSystemMove = false
                onCanceled: awaitingSystemMove = false
                onPressed: function(mouse) {
                    // Cocoa can deliver the Qt press while currentEvent is an
                    // application event. Retry only during this held gesture.
                    const moved = window.startSystemMove()
                    awaitingSystemMove = !moved
                    // The OS can consume release; relinquish QML ownership.
                    if (moved) mouse.accepted = false
                }
                onPositionChanged: function(mouse) {
                    if (!awaitingSystemMove || !pressed || !(mouse.buttons & Qt.LeftButton)) return
                    if (window.startSystemMove()) {
                        awaitingSystemMove = false
                        // The OS may consume release after a retry too. Retire
                        // the QML press so the next press is independently heard.
                        visible = false
                        Qt.callLater(function() { headerDragArea.visible = true })
                    }
                }
            }

            Row {
                id: brandRow
                objectName: "brandRow"
                x: focusHeader.nativeHeaderInset
                y: Math.round((44 - height) / 2)
                // Canonical lockup: 13px gap at 191px painted mark height.
                // Account for this mark export's 8px transparent right edge.
                spacing: (36 * 400 / 410) * 13 / 191 - 36 * 8 / 410
                Image {
                    objectName: "brandMark"
                    source: assetUrl + "brand/vf-mark.png"
                    width: 36 * 468 / 410; height: 36
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                Row {
                    visible: !focusHeader.compact
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0
                    Text {
                        objectName: "brandVodText"
                        text: "VOD"
                        color: theme.accent
                        font.pixelSize: 19
                        font.bold: true
                    }
                    Text {
                        objectName: "brandForgeText"
                        text: "Forge"
                        color: "#ffffff"
                        font.pixelSize: 19
                        font.bold: true
                    }
                }
            }
            Row {
                id: navigationRow
                objectName: "navigationRow"
                x: focusHeader.stacked ? 0 : focusHeader.brandWidth + (focusHeader.compact ? 4 : 3)
                y: focusHeader.stacked ? 56 : 0
                spacing: 10
                Repeater {
                    model: ["Forge", "Library", "Watch", "Activity"]
                    StoneButton {
                        required property string modelData
                        objectName: "navigationButton_" + modelData
                        label: modelData
                        selected: bridge.selection === modelData
                        icon: "image://vodforge/icon/" + (
                            modelData === "Forge" ? "download.png" :
                            modelData === "Library" ? "folder.png" :
                            modelData === "Watch" ? "play.png" : "activity.png") + "/r" + bridge.themeRevision
                        width: Math.max(86, implicitWidth)
                        height: implicitHeight
                        Rectangle {
                            objectName: "navigationSelectedBar_" + modelData
                            visible: parent.selected
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 5
                            width: parent.width - 28
                            height: 2
                            radius: 1
                            color: theme.accent
                        }
                        onActivated: {
                            const keepPlaying = window.miniPlayerActive ||
                                (window.mediaPlayer && window.mediaPlayer.playbackState === MediaPlayer.PlayingState)
                            window.miniPlayerActive = !!keepPlaying
                            bridge.selectHome(modelData, !!keepPlaying)
                        }
                    }
                }
            }
            Row {
                id: utilitiesRow
                objectName: "utilitiesRow"
                anchors.right: parent.right
                y: 1
                spacing: 8
                StoneField {
                    objectName: "globalSearchField"
                    visible: bridge.selection === "Library" || bridge.selection === "Watch"
                    width: focusHeader.searchWidth
                    height: 40
                    focused: searchInput.activeFocus
                    TextField {
                        id: searchInput
                        objectName: "headerSearchInput"
                        Accessible.name: bridge.selection === "Watch" ? "Search saved videos" : "Search library"
                        anchors.fill: parent
                        anchors.leftMargin: 15
                        anchors.rightMargin: 12
                        placeholderText: bridge.selection === "Watch" ? "Search saved videos…" : "Search your library…"
                        text: bridge.activeSearch
                        color: theme.text
                        placeholderTextColor: theme.muted
                        background: Item {}
                        font.pixelSize: 15
                        onTextEdited: bridge.setActiveSearch(text)
                    }
                }
                StoneButton {
                    objectName: "headerXButton"
                    sceneIcon: "x"
                    quiet: true
                    accessibilityLabel: "VODForge on X"
                    width: 28; height: 40
                    onActivated: bridge.openSocialAccount()
                    LiquidToolTip { visible: parent.hovered; text: "VODForge on X" }
                }
                StoneButton {
                    objectName: "headerSettingsButton"
                    icon: "image://vodforge/icon/settings.png/r" + bridge.themeRevision
                    accessibilityLabel: "Settings"
                    width: 28; height: 40
                    onActivated: settingsPopup.toggleFrom(this)
                }
            }
        }

        Rectangle {
            objectName: "focusHeaderDivider"
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            Layout.topMargin: 0
            color: theme.border
        }

        ScrollView {
            id: forgeViewport
            objectName: "forgeViewport"
            implicitHeight: 0
            implicitWidth: 0
            visible: bridge.selection === "Forge"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 0
            Layout.leftMargin: window.forgeHorizontalPad
            Layout.rightMargin: window.forgeHorizontalPad
            Layout.topMargin: window.forgeTopPad - 2
            clip: true
            contentWidth: availableWidth
            contentHeight: forgeScene.height
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ColumnLayout {
            id: forgeScene
            objectName: "forgeScene"
            width: forgeViewport.availableWidth
            height: Math.max(forgeViewport.availableHeight, implicitHeight)
            spacing: 8

            RowLayout {
                id: forgeCommandRow
                objectName: "forgeCommandRow"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: 48
                spacing: 8
                StoneField {
                    objectName: "forgeUrlField"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48
                    Layout.rightMargin: 4
                    focused: urlInput.activeFocus
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 16
                        anchors.rightMargin: 9
                        Image {
                            source: "image://vodforge/icon/link-2.png/r" + bridge.themeRevision
                            Layout.preferredWidth: 25
                            Layout.preferredHeight: 20
                            fillMode: Image.PreserveAspectFit
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
                            onTextChanged: { if (bridge) bridge.sourceInputChanged(text) }
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
                            onActivated: { formatMenu.anchorItem = this; formatMenu.toggleFrom(this) }
                        }
                    }
                }
                StoneButton {
                    objectName: "forgeDownloadButton"
                    label: bridge.running ? "Queue" : "Download"
                    emphasized: true
                    primary: true
                    Layout.preferredWidth: 131
                    Layout.preferredHeight: 44
                    onActivated: bridge.submit(urlInput.text, window.outputFormat)
                }
                StoneButton {
                    objectName: "forgeOptionsButton"
                    label: "Options"
                    Layout.preferredWidth: 106
                    Layout.preferredHeight: 46
                    onActivated: window.outputFormat === "MP3" ? mp3OptionsPopup.toggleFrom(this) : optionsMenu.toggleFrom(this)
                }
            }

            RowLayout {
                id: forgeLocalRow
                objectName: "forgeLocalRow"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: 44
                spacing: 12
                StoneButton {
                    objectName: "forgeLoadListButton"
                    label: bridge.batchSummary === "No URL list loaded" ? "Load URL list" : "List loaded"
                    Layout.preferredWidth: 131
                    Layout.preferredHeight: 44
                    onActivated: urlListDialog.open()
                }
                RowLayout {
                    id: forgeComposerAuxRow
                    spacing: 6
                    Text {
                        text: "Save to"
                        color: theme.text
                        font.pixelSize: 15
                        Layout.leftMargin: 7
                        Layout.preferredWidth: 52
                    }
                    OutputPathField {
                        objectName: "forgeDestinationField"
                        Layout.preferredWidth: window.forgeDensity === "compact" ? 170 : window.forgeDensity === "balanced" ? 210 : 240
                        Layout.preferredHeight: 34
                        path: bridge.outputPath
                        interactive: true
                        accessibilityLabel: "Choose output folder"
                        onActivated: window.openOutputFolderDialog()
                    }
                }
                Item { Layout.fillWidth: true }
                Text { text: "Have local audio?"; visible: window.width >= 880; color: theme.muted; font.pixelSize: 15 }
                StoneButton {
                    objectName: "forgeCreateVideoButton"
                    label: "Create video"
                    Layout.preferredWidth: 131
                    Layout.preferredHeight: 44
                    onActivated: localConversionPopup.toggleFrom(this)
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: window.compactHeight ? 70 : 128
                Layout.topMargin: window.compactHeight ? 4 : 16
                spacing: window.compactHeight ? 16 : 28
                Item {
                    objectName: "forgeHeroArtwork"
                    Layout.preferredWidth: window.compactHeight ? 120 : 152
                    Layout.preferredHeight: window.compactHeight ? 68 : 86
                    ArtworkImage {
                        objectName: "forgeHeroMediaImage"
                        anchors.fill: parent
                        source: window.selectedForgeRun.artwork || ""
                        inset: 0
                    }
                    Image {
                        anchors.centerIn: parent
                        width: window.compactHeight ? 48 : 68
                        height: width
                        visible: !window.selectedForgeRun.artwork
                        source: assetUrl + "brand/icon-180.png"
                        fillMode: Image.PreserveAspectFit
                        smooth: true
                    }
                    Rectangle {
                        objectName: "forgeHeroDurationBadge"
                        visible: !!window.selectedForgeRun.duration
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        anchors.rightMargin: 6
                        anchors.bottomMargin: 6
                        width: durationText.implicitWidth + 8
                        height: durationText.implicitHeight + 2
                        color: "#08090a"
                        Text {
                            id: durationText
                            anchors.centerIn: parent
                            text: window.selectedForgeRun.duration || ""
                            color: "#ffffff"
                            font.pixelSize: 10
                            font.bold: true
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredWidth: 1
                    spacing: window.compactHeight ? 3 : 7
                    Text {
                        objectName: "forgeSelectedTitle"
                        text: window.selectedForgeRun.title || "Ready for a new run"
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
                        color: theme.text
                        font.pixelSize: window.compactHeight ? 21 : 24
                        font.bold: true
                    }
                    Text {
                        objectName: "forgeSelectedStatus"
                        text: window.selectedForgeRun.status ||
                              "Paste a video URL above, then press Return to begin."
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
                        color: runStatusTone.colorFor(window.selectedForgeRun.kind,
                                                      window.selectedForgeToneStatus, theme)
                        font.pixelSize: window.compactHeight ? 13 : 15
                    }
                    Text {
                        text: window.selectedForgeRun.detail ||
                              (window.selectedForgeRun.kind === "active" ? bridge.quality + "  ·  " + bridge.exportModeLabel : "")
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        elide: Text.ElideRight
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
                Text {
                    objectName: "forgeSelectedProgressLabel"
                    text: window.showingForgePreview ?
                          (bridge.forgePreview.phase === "failed" ? "Failed" : "…") :
                          runStatusTone.progressLabel(window.selectedForgeRun.kind,
                                                      window.selectedForgeRun.status,
                                                      window.selectedForgeRun.progress)
                    color: runStatusTone.colorFor(window.selectedForgeRun.kind,
                                                  window.selectedForgeToneStatus, theme)
                    font.pixelSize: window.selectedForgeRun.kind === "terminal" ?
                                        (window.compactHeight ? 18 : 22) :
                                        (window.compactHeight ? 28 : 34)
                }
            }

            RunProgress {
                objectName: "forgeSelectedProgress"
                Layout.fillWidth: true
                Layout.preferredHeight: 5
                kind: window.selectedForgeRun.kind || ""
                status: window.selectedForgeToneStatus
                progress: window.selectedForgeRun.progress || 0
            }

            RowLayout {
                visible: window.forgeDensity !== "compact"
                Layout.fillWidth: true
                Text {
                    text: window.selectedForgeRun.kind === "completed" ?
                          "Showing completed run: " + window.selectedForgeRun.title :
                          window.selectedForgeRun.kind === "terminal" ?
                          "Showing " + window.selectedForgeRun.status.toLowerCase() + " run: " + window.selectedForgeRun.title :
                          window.selectedForgeRun.kind === "queued" ?
                          "Showing queued run: " + window.selectedForgeRun.title :
                          window.selectedForgeRun.kind === "active" ? window.selectedForgeRun.status :
                          bridge.history.length ? "Loaded " + bridge.history.length + " downloaded media item(s) from history." : "Ready for a new run."
                    color: theme.muted; font.pixelSize: 14
                    Layout.fillWidth: true; elide: Text.ElideRight
                }
                Row {
                    id: forgeCompletedActions
                    objectName: "forgeCompletedActions"
                    readonly property string owner: window.selectedForgeRun.kind === "completed" ?
                                                        (window.selectedForgeRun.owner || "") : ""
                    visible: owner.length > 0
                    spacing: 8
                    StoneButton {
                        objectName: "forgeCompletedPlay"
                        deepHover: true
                        label: "Play"; primary: true; size: "inline"
                        width: 84
                        onActivated: bridge.openLibraryOwner(forgeCompletedActions.owner)
                    }
                    StoneButton {
                        objectName: "forgeCompletedShowInLibrary"
                        deepHover: true
                        label: "Show in Library"; size: "inline"
                        width: 142
                        onActivated: { if (bridge.openLibraryDetails(forgeCompletedActions.owner)) bridge.select("Library") }
                    }
                    StoneButton {
                        objectName: "forgeCompletedShowInFolder"
                        deepHover: true
                        label: "Show in Folder"; size: "inline"
                        width: 136
                        onActivated: bridge.openLibraryFolder(forgeCompletedActions.owner)
                    }
                }
                Text {
                    visible: !forgeCompletedActions.visible
                    text: window.selectedForgeRun.kind === "completed" ? "Complete / Ready to open in Library" :
                          window.selectedForgeRun.kind === "terminal" ? window.selectedForgeRun.status + " / Retry is available" :
                          window.selectedForgeRun.kind === "queued" ? "Queued / Waiting for the current run" :
                          window.showingForgePreview ? "Metadata only / No media is being downloaded" :
                          window.outputFormat === "MP4" ? "VOD-ready MP4 / H.264 video / AAC audio" :
                          window.outputFormat === "MP3" ? "Audio-only MP3 / best YouTube audio source" :
                          "Original audio / No re-encoding"
                    color: theme.muted; font.pixelSize: 14
                    elide: Text.ElideRight
                    Layout.maximumWidth: window.width * 0.42
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: window.compactHeight ? 116 : 185
                Layout.minimumHeight: window.compactHeight ? 157 : 185
                spacing: 16
                ColumnLayout {
                    id: forgeLivePane
                    objectName: "forgeLivePane"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    spacing: 9
                    property bool technical: false
                    RowLayout {
                        visible: window.forgeDensity === "compact"
                        Layout.fillWidth: true
                        Text {
                            text: "LIVE ACTIVITY"
                            color: theme.muted; font.pixelSize: 14
                            Layout.fillWidth: true; elide: Text.ElideRight
                        }
                        StoneButton {
                            visible: window.forgeDensity === "compact"
                            label: "Output details"
                            size: "inline"
                            Layout.preferredWidth: 116
                            onActivated: outputDetailsPopup.toggleFrom(this)
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 8
                        ActivityModeSlider {
                            id: forgeActivityMode
                            objectName: "forgeActivityModeSlider"
                            technical: forgeLivePane.technical
                            Layout.alignment: Qt.AlignTop
                            onSelected: function(value) {
                                forgeLivePane.technical = value
                                if (value) bridge.openTechnicalDetails()
                            }
                        }
                        ScrollView {
                            id: forgeActivityViewport
                            objectName: "forgeActivityViewport"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            contentWidth: availableWidth
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            ActivityLines {
                                objectName: "forgeActivityLines"
                                width: forgeActivityViewport.availableWidth
                                technical: forgeLivePane.technical
                                activityText: window.showingForgePreview ?
                                      "Metadata only — no media is being downloaded" :
                                      forgeLivePane.technical ? bridge.forgeActivity.technical : bridge.forgeActivity.friendly
                            }
                        }
                    }
                    RowLayout {
                        visible: bridge.running && !window.compactHeight
                        spacing: 8
                        StoneButton {
                            objectName: "forgeControl0"
                            property var action: (bridge.runControls || [])[0] || ({})
                            visible: !!action.label
                            label: action.label || ""
                            Accessible.description: action.description || ""
                            LiquidToolTip { visible: parent.hovered; text: parent.action.description || "" }
                            Layout.preferredHeight: 36
                            onActivated: {
                                if (action.operation === "cancel") bridge.cancel()
                                else if (action.operation === "skip_item") bridge.skipItem()
                                else bridge.skipSource()
                            }
                        }
                        StoneButton {
                            objectName: "forgeControl1"
                            property var action: (bridge.runControls || [])[1] || ({})
                            visible: !!action.label
                            label: action.label || ""
                            Accessible.description: action.description || ""
                            LiquidToolTip { visible: parent.hovered; text: parent.action.description || "" }
                            Layout.preferredHeight: 36
                            onActivated: {
                                if (action.operation === "cancel") bridge.cancel()
                                else if (action.operation === "skip_item") bridge.skipItem()
                                else bridge.skipSource()
                            }
                        }
                        StoneButton {
                            objectName: "forgeControl2"
                            property var action: (bridge.runControls || [])[2] || ({})
                            visible: !!action.label
                            label: action.label || ""
                            Accessible.description: action.description || ""
                            LiquidToolTip { visible: parent.hovered; text: parent.action.description || "" }
                            Layout.preferredHeight: 36
                            onActivated: {
                                if (action.operation === "cancel") bridge.cancel()
                                else if (action.operation === "skip_item") bridge.skipItem()
                                else bridge.skipSource()
                            }
                        }
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
                Rectangle {
                    id: forgeDetailsDivider
                    objectName: "forgeDetailsDivider"
                    visible: window.forgeDensity !== "compact"
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    color: theme.border
                }
                ScrollView {
                    id: forgeSourceDetailsViewport
                    objectName: "forgeSourceDetailsViewport"
                    visible: window.forgeDensity !== "compact"
                    Layout.fillWidth: true
                    Layout.preferredWidth: 1
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ForgeSourceDetails {
                        width: forgeSourceDetailsViewport.availableWidth
                        appBridge: bridge
                        outputFormat: window.outputFormat
                        displayType: window.forgeDisplayType
                        preview: window.showingForgePreview
                        // Pending choices refresh live; selected-run facts retain their job snapshot.
                selectedFacts: (bridge.outputFormat, bridge.exportMode, bridge.quality,
                                bridge.outputPath, bridge.downloadOptions, bridge.nvencAvailable,
                                bridge.manualValues, bridge.mp3Values, bridge.cookieSource,
                                bridge.cookieBrowser, bridge.extraTags, bridge.batchSummary,
                                bridge.forgeSelectedFacts)
                        showHeading: false
                    }
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
            }
        }
        }

        LibraryScene {
            id: libraryBrowseScene
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
            onActionsRequested: function(owner, anchor, scrollViewport) {
                window.selectedSavedOwner = owner
                libraryItemPopup.anchorItem = anchor
                libraryItemPopup.scrollViewport = scrollViewport
                libraryItemPopup.toggleFrom(anchor)
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
                        collectionTargetPopup.selectedOwners = annotationOwners
                        collectionTargetPopup.open()
                    }
                } else if (action === "move") {
                    window.pendingFileOwners = owners.slice()
                    libraryMoveFolderDialog.open()
                } else if (action === "delete") {
                    if (bridge.startFileActions("delete", owners, Qt.url("")))
                        fileActionPopup.open()
                }
            }
            onImportRequested: libraryImportDialog.open()
        }
        WatchScene {
            id: watchBrowseScene
            objectName: "watchBrowseScene"
            visible: bridge.selection === "Watch" &&
                     (bridge.playbackUrl.toString().length === 0 || window.miniPlayerActive)
            Layout.fillWidth: true
            Layout.fillHeight: true
            appBridge: bridge
        }
        PlayerScene {
            id: playerScene
            objectName: "watchPlayerScene"
            visible: bridge.selection === "Watch" && bridge.playbackUrl.toString().length > 0 &&
                     !window.miniPlayerActive
            Layout.fillWidth: true
            Layout.fillHeight: true
            appBridge: bridge
            player: window.mediaPlayer
            volume: window.playerVolume
            onCloseRequested: {
                playerScene.presentationMode = "embedded"
                if (window.mediaPlayer && window.mediaPlayer.playbackState === MediaPlayer.PlayingState) {
                    window.miniPlayerActive = true
                    bridge.returnToPlaybackOrigin()
                } else {
                    bridge.closePlayback()
                }
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

    Item {
        id: miniPlayer
        objectName: "miniPlayer"
        parent: window.contentItem
        z: 100
        width: 272
        height: 182
        visible: window.miniPlayerActive && bridge.playbackUrl.toString().length > 0
        function snap() {
            x = window.miniPlayerCorner % 2 ? window.width - width - 16 : 16
            y = window.miniPlayerCorner >= 2 ? window.height - height - 16 : 62
        }
        onVisibleChanged: { if (visible) Qt.callLater(snap) }
        Connections {
            target: window
            function onWidthChanged() { if (miniPlayer.visible) miniPlayer.snap() }
            function onHeightChanged() { if (miniPlayer.visible) miniPlayer.snap() }
        }
        HoverHandler { id: miniHover }
        StoneField { anchors.fill: parent }
        VideoOutput {
            id: miniVideoSurface
            objectName: "miniVideoSurface"
            x: 6; y: 6; width: parent.width - 12; height: 145
            fillMode: VideoOutput.PreserveAspectFit
            endOfStreamPolicy: VideoOutput.KeepLastFrame
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.OpenHandCursor
            drag.target: miniPlayer
            drag.minimumX: 8
            drag.maximumX: window.width - miniPlayer.width - 8
            drag.minimumY: 56
            drag.maximumY: window.height - miniPlayer.height - 8
            onClicked: window.expandMiniPlayer()
            onReleased: {
                if (!miniPlayer.visible) return
                window.miniPlayerCorner = (miniPlayer.y + miniPlayer.height / 2 < window.height / 2 ? 0 : 2) +
                    (miniPlayer.x + miniPlayer.width / 2 < window.width / 2 ? 0 : 1)
                miniPlayer.snap()
            }
        }
        Text {
            x: 10; y: 155; width: parent.width - 20
            text: bridge.playerScene.title || "Playing video"
            color: theme.text; font.pixelSize: 12; elide: Text.ElideRight
        }
        Row {
            visible: miniHover.hovered
            x: 10; y: 10; spacing: 5
            StoneButton {
                objectName: "miniPlayerPause"
                sceneIcon: window.mediaPlayer && window.mediaPlayer.playbackState === MediaPlayer.PlayingState ? "pause" : "play"
                accessibilityLabel: sceneIcon === "pause" ? "Pause mini player" : "Play mini player"
                width: 32; height: 30
                onActivated: {
                    if (!window.mediaPlayer) return
                    if (window.mediaPlayer.playbackState === MediaPlayer.PlayingState) window.mediaPlayer.pause()
                    else window.mediaPlayer.play()
                }
            }
        }
        StoneButton {
            objectName: "miniPlayerClose"
            visible: miniHover.hovered
            x: parent.width - width - 10; y: 10
            label: "×"; accessibilityLabel: "Close mini player"
            width: 32; height: 30
            onActivated: {
                bridge.closePlayback(true)
            }
        }
    }

    StonePopup {
        id: missingMediaPopup
        objectName: "missingMediaPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(620, window.width - 30)
        height: 280
        padding: 18
        modal: true
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
    StonePopup {
        id: relinkPopup
        objectName: "relinkPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(560, window.width - 30)
        height: 335
        padding: 18
        modal: true
        closePolicy: bridge.relinkInfo.phase === "working" ? Popup.NoAutoClose : Popup.CloseOnEscape
        onClosed: {
            if (bridge.relinkInfo.phase === "checking" || bridge.relinkInfo.phase === "preview") bridge.cancelRelink()
        }
        ColumnLayout {
            anchors.fill: parent; spacing: 12
            Text { text: bridge.relinkInfo.mode === "folder" ? "Locate moved files" : "Update saved file location"; color: theme.text; font.pixelSize: 22; font.bold: true; Layout.fillWidth: true }
            Text { visible: bridge.relinkInfo.mode === "folder"; text: "Recorded folder: " + bridge.relinkInfo.source; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideMiddle }
            Text { text: "Chosen location: " + bridge.relinkInfo.destination; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideMiddle }
            Text { visible: bridge.relinkInfo.mode === "folder"; text: bridge.relinkInfo.readyCount + " of " + bridge.relinkInfo.selectedCount + " saved files found"; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true }
            Text { visible: bridge.relinkInfo.mode === "folder"; text: "Files in subfolders keep the same relative path. This updates Library references only; no files are moved."; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true; wrapMode: Text.WordWrap }
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
    AnchoredPopup {
        id: libraryItemPopup
        objectName: "librarySavedActionsPopup"
        parent: window.contentItem
        preferAbove: true
        alignRight: true
        width: 260
        height: 342
        padding: 8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        ColumnLayout {
            anchors.fill: parent
            spacing: 5
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
    StonePopup {
        id: fileActionPopup
        objectName: "libraryFileActionPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(490, window.width - 40)
        height: Math.min(window.height - 40,
                fileActionContent.implicitHeight + topPadding + bottomPadding)
        padding: 18
        modal: true
        closePolicy: bridge.fileActionBusy ? Popup.NoAutoClose : Popup.CloseOnEscape
        ColumnLayout {
            id: fileActionContent
            anchors.fill: parent
            spacing: 12
            Text {
                id: fileActionHeading
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                text: bridge.fileActionRecovery ? "Review interrupted file change" :
                    bridge.fileActionName === "move" ? "Move saved media" : "Saved media files"
                color: theme.text
                font.pixelSize: 21
                font.bold: true
            }
            ScrollView {
                id: fileActionBody
                objectName: "fileActionBodyScroll"
                Layout.fillWidth: true
                // Long reports scroll inside the same shared shell; footer stays visible.
                Layout.preferredHeight: Math.min(fileActionMessage.implicitHeight,
                    Math.max(48, window.height - 40 - fileActionPopup.topPadding -
                        fileActionPopup.bottomPadding - fileActionHeading.implicitHeight -
                        fileActionFooter.implicitHeight -
                        (fileActionReviewRow.visible ? fileActionReviewRow.implicitHeight : 0) -
                        fileActionContent.spacing * (fileActionReviewRow.visible ? 3 : 2)))
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                Text {
                    id: fileActionMessage
                    objectName: "fileActionBodyMessage"
                    text: bridge.fileActionStatus
                    color: theme.muted
                    font.pixelSize: 15
                    wrapMode: Text.WordWrap
                    width: fileActionBody.availableWidth
                }
            }
            RowLayout {
                id: fileActionReviewRow
                visible: !!bridge.fileActionReviewOwner
                Layout.fillWidth: true
                StoneButton {
                    objectName: "fileActionFindFile"
                    label: "Find saved file…"
                    Layout.fillWidth: true
                    onActivated: {
                        window.pendingRelinkOwner = bridge.fileActionReviewOwner
                        fileActionPopup.close()
                        relinkFileDialog.open()
                    }
                }
                StoneButton {
                    objectName: "fileActionForgetCard"
                    label: "Remove Library card"
                    Layout.fillWidth: true
                    onActivated: {
                        if (bridge.prepareLibraryRemoval(bridge.fileActionReviewOwner)) {
                            fileActionPopup.close()
                            libraryRemovalPopup.open()
                        }
                    }
                }
            }
            RowLayout {
                id: fileActionFooter
                Layout.fillWidth: true
                StoneButton {
                    objectName: "fileActionConfirmButton"
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
                    objectName: "fileActionDismissButton"
                    label: bridge.fileActionName === "move" && bridge.fileActionEligible ? "Cancel" : "Close"
                    enabled: !bridge.fileActionBusy
                    Layout.preferredWidth: 90
                    Layout.preferredHeight: 40
                    onActivated: fileActionPopup.close()
                }
            }
        }
    }
    StonePopup {
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
    StonePopup {
        id: collectionPopup
        objectName: "libraryCollectionPopup"
        property var selectionPreset: []
        property var selectedOwners: []
        property string pickerMode: "videos"
        property string pickerSearch: ""
        function toggleOwners(owners) {
            const next = selectedOwners.slice()
            const allSelected = owners.every(owner => next.indexOf(owner) >= 0)
            for (const owner of owners) {
                const index = next.indexOf(owner)
                if (allSelected && index >= 0) next.splice(index, 1)
                else if (!allSelected && index < 0) next.push(owner)
            }
            selectedOwners = next
        }
        onOpened: {
            selectedOwners = selectionPreset.slice()
            pickerMode = "videos"
            pickerSearch = ""
            collectionName.text = ""
        }
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(680, window.width - 40)
        height: Math.min(620, window.height - 40)
        padding: 20
        modal: true
        ColumnLayout {
            anchors.fill: parent
            spacing: 12
            Text { text: "Create a collection"; color: theme.text; font.pixelSize: 23; font.bold: true }
            Text {
                text: "Choose individual media or select every item in a playlist or channel."
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
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Repeater {
                    model: ["videos", "playlists", "channels"]
                    StoneButton {
                        required property string modelData
                        label: modelData.charAt(0).toUpperCase() + modelData.slice(1)
                        selected: collectionPopup.pickerMode === modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        onActivated: collectionPopup.pickerMode = modelData
                    }
                }
            }
            StoneField {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                TextField {
                    objectName: "collectionPickerSearch"
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    placeholderText: "Search media or groups…"
                    text: collectionPopup.pickerSearch
                    onTextEdited: collectionPopup.pickerSearch = text
                    color: theme.text
                    background: Item {}
                }
            }
            ListView {
                id: collectionPickerList
                objectName: "collectionPickerList"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 5
                model: collectionPopup.visible ? (bridge.collectionPicker[collectionPopup.pickerMode] || []).filter(
                    row => row.title.toLowerCase().indexOf(collectionPopup.pickerSearch.toLowerCase()) >= 0 ||
                           (row.creator || "").toLowerCase().indexOf(collectionPopup.pickerSearch.toLowerCase()) >= 0
                ) : []
                delegate: StoneButton {
                    id: pickerCard
                    required property var modelData
                    readonly property var owners: collectionPopup.pickerMode === "videos" ? [modelData.owner] : modelData.owners
                    objectName: "collectionPickerCard"
                    width: collectionPickerList.width
                    height: 72
                    label: ""
                    accessibilityLabel: (collectionPopup.pickerMode === "videos" ? "Select media " : "Select all in ") + modelData.title
                    selected: owners.every(owner => collectionPopup.selectedOwners.indexOf(owner) >= 0)
                    onActivated: collectionPopup.toggleOwners(owners)
                    ArtworkImage {
                        objectName: "collectionPickerArtwork"
                        x: pickerCard.artworkFaceInset
                        y: pickerCard.artworkFaceInset
                        width: 86
                        height: pickerCard.height - 2 * pickerCard.artworkFaceInset
                        cover: true
                        inset: 0
                        source: bridge.mediaArtwork(pickerCard.modelData.artworkOwner)
                    }
                    Column {
                        x: 103
                        y: 11
                        width: parent.width - 150
                        spacing: 5
                        Text { width: parent.width; text: pickerCard.modelData.title; color: theme.text; font.pixelSize: 14; font.bold: true; elide: Text.ElideRight }
                        Text {
                            width: parent.width
                            text: collectionPopup.pickerMode === "videos" ?
                                pickerCard.modelData.creator + " · " + (pickerCard.modelData.playlist || "No playlist") +
                                (pickerCard.modelData.exportCount > 1 ? " · " + pickerCard.modelData.exportCount + " exports" : "") :
                                "Select all " + pickerCard.modelData.count + " saved item" + (pickerCard.modelData.count === 1 ? "" : "s")
                            color: theme.muted; font.pixelSize: 12; elide: Text.ElideRight
                        }
                    }
                    Text {
                        x: parent.width - 38; y: 21; width: 25
                        text: pickerCard.selected ? "✓" : "○"
                        color: pickerCard.selected ? theme.accent : theme.muted
                        font.pixelSize: 22
                    }
                }
            }
            Text { text: collectionPopup.selectedOwners.length + " selected"; color: theme.muted; font.pixelSize: 13; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Cancel"; Layout.preferredWidth: 95; Layout.preferredHeight: 40; onActivated: collectionPopup.close() }
                StoneButton {
                    label: "Save"
                    enabled: collectionName.text.trim().length > 0 && collectionPopup.selectedOwners.length > 0
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
    StonePopup {
        id: collectionTargetPopup
        objectName: "libraryCollectionTargetPopup"
        property var selectedOwners: []
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(420, window.width - 40)
        height: Math.min(430, window.height - 40)
        padding: 16
        modal: true
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Text { text: "Add to collection"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text { text: collectionTargetPopup.selectedOwners.length + " selected item(s)"; color: theme.muted; font.pixelSize: 13 }
            ListView {
                id: collectionTargetList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 5
                model: bridge.libraryCategories.slice(1)
                delegate: StoneButton {
                    required property string modelData
                    width: collectionTargetList.width
                    height: 44
                    label: modelData
                    onActivated: {
                        if (bridge.addToCollection(modelData, collectionTargetPopup.selectedOwners))
                            collectionTargetPopup.close()
                    }
                }
            }
            Text {
                visible: collectionTargetList.count === 0
                text: "No collections yet. Create one for these items."
                color: theme.muted
                font.pixelSize: 13
            }
            StoneButton {
                label: "Create new collection…"
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                onActivated: {
                    collectionPopup.selectionPreset = collectionTargetPopup.selectedOwners.slice()
                    collectionTargetPopup.close()
                    collectionPopup.open()
                }
            }
        }
    }
    StonePopup {
        id: annotationPopup
        objectName: "libraryAnnotationPopup"
        onClosed: annotationCategoryMenu.close()
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(570, window.width - 40)
        height: 450
        padding: 18
        modal: true
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
                    objectName: "annotationCategoryInput"
                    // A mouse-focus open leaves editing focus in this field.
                    // Escape dismisses its suggestions before the whole dialog.
                    Keys.onEscapePressed: event => {
                        if (annotationCategoryMenu.visible) annotationCategoryMenu.close()
                        else event.accepted = false
                    }
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 46
                    padding: 0; verticalAlignment: TextInput.AlignVCenter
                    text: bridge.annotationValues.category
                    placeholderText: "Optional category"
                    color: theme.text; placeholderTextColor: theme.muted
                    font.pixelSize: 15; background: Item {}
                    onActiveFocusChanged: {
                        // Closing the list restores focus here. That return is
                        // not a fresh request to open it again.
                        if (activeFocus && focusReason !== Qt.PopupFocusReason &&
                                bridge.libraryCategories.length > 1) {
                            annotationCategoryMenu.anchorItem = parent
                            annotationCategoryMenu.open()
                        }
                    }
                }
                StoneButton {
                    id: annotationCategoryButton
                    objectName: "annotationCategoryButton"
                    x: parent.width - 40; y: 3; width: 36; height: 34
                    label: "▾"; size: "inline"
                    onActivated: { annotationCategoryMenu.anchorItem = parent; annotationCategoryMenu.toggleFrom(this) }
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
    AnchoredPopup {
        id: annotationCategoryMenu
        objectName: "annotationCategoryMenu"
        // Focus can open the list before the arrow has ever been activated.
        triggerItem: annotationCategoryButton
        parent: window.contentItem
        width: Math.min(360, annotationPopup.width - 36)
        height: Math.min(250, bridge.libraryCategories.slice(1).length * 41 + 8)
        padding: 4
        ScrollView {
            anchors.fill: parent
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: parent.width
                spacing: 1
                Repeater {
                    model: bridge.libraryCategories.slice(1)
                    StoneButton {
                        required property string modelData
                        width: parent.width; height: 40
                        label: modelData
                        onActivated: { categoryInput.text = modelData; annotationCategoryMenu.close() }
                    }
                }
            }
        }
    }
    StonePopup {
        id: mp3OptionsPopup
        objectName: "mp3OptionsPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(560, window.width - 40)
        height: 420
        padding: 18
        modal: true
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
                            var next = choices[(choices.indexOf(bridge.mp3Values[modelData.key]) + 1) % choices.length]
                            if (modelData.key === "mp3_cover_art_mode" && next === "Custom art" && !bridge.mp3CoverAvailable)
                                mp3CoverDialog.open()
                            else
                                bridge.setMp3Value(modelData.key, next)
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
                StoneButton { label: "Replace image"; Layout.preferredWidth: 130; Layout.preferredHeight: 38; onActivated: mp3CoverDialog.open() }
                StoneButton { label: "Clear"; Layout.preferredWidth: 64; Layout.preferredHeight: 38; onActivated: bridge.clearMp3Cover() }
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Done"; Layout.preferredWidth: 84; Layout.preferredHeight: 40; onActivated: mp3OptionsPopup.close() }
            }
        }
    }
    StonePopup {
        id: settingsPopup
        objectName: "downloadSettingsPopup"
        onClosed: { translatedSubtitleMenu.close(); settingsQualityMenu.close(); settingsOutputModeMenu.close(); appearanceThemeMenu.close(); helpMenu.close() }
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
        y: 66
        width: Math.min(820, window.width - 70)
        height: Math.min(752, window.height - y - 12)
        padding: 18
        modal: true
        ColumnLayout {
            anchors.fill: parent
            spacing: 7
            RowLayout {
                Layout.fillWidth: true
                Text { objectName: "settingsTitle"; text: "Settings"; color: theme.text; font.pixelSize: 21; font.bold: true; Layout.fillWidth: true }
                StoneButton {
                    id: proButton
                    objectName: "settingsProButton"
                    label: ""
                    accessibilityLabel: "VODForge PRO"
                    Layout.preferredWidth: 150
                    Layout.preferredHeight: 40
                    Row {
                        anchors.centerIn: parent
                        spacing: 0
                        Text { objectName: "settingsProVod"; text: "VOD"; color: theme.accent; font.family: buttonFontFamily; font.pixelSize: buttonMetrics.default.fontPixels }
                        Text { objectName: "settingsProForge"; text: "Forge"; color: theme.text; font.family: buttonFontFamily; font.pixelSize: buttonMetrics.default.fontPixels }
                        Text { objectName: "settingsProSuffix"; text: " PRO"; color: theme.accent; font.family: buttonFontFamily; font.pixelSize: buttonMetrics.default.fontPixels }
                    }
                    onActivated: bridge.openCloudEarlyAccess()
                }
            }
            Text { objectName: "settingsSubtitle"; Layout.minimumWidth: 0; Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "These choices apply to new downloads and are saved as you change them."; color: theme.muted; font.pixelSize: 14 }
            ScrollView {
                id: settingsBody
                objectName: "settingsBodyViewport"
                Layout.minimumWidth: 0
                contentWidth: availableWidth
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
                            objectName: "settingsLeftColumn"
                            Layout.fillWidth: true
                            Layout.preferredWidth: 360
                            Layout.alignment: Qt.AlignTop
                            spacing: 12
                    Text { text: "SAVE LOCATION"; color: theme.accent; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        Layout.fillWidth: true
                        StoneField {
                            Layout.fillWidth: true; Layout.preferredHeight: 42
                            HoverHandler { id: settingsDestinationHover }
                            LiquidToolTip { visible: settingsDestinationHover.hovered; text: bridge.outputPath }
                            Text { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; verticalAlignment: Text.AlignVCenter; text: bridge.outputPath; color: theme.text; elide: Text.ElideMiddle; font.pixelSize: 14 }
                        }
                        StoneButton { label: "Browse"; Layout.preferredWidth: 95; Layout.preferredHeight: 40; LiquidToolTip { visible: parent.hovered; text: bridge.outputPath } onActivated: window.openOutputFolderDialog() }
                    }
                    Text { text: "BATCH AND PLAYLISTS"; color: theme.accent; font.pixelSize: 13; font.bold: true }
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
                    Text { text: "YOUTUBE ACCESS"; color: theme.accent; font.pixelSize: 13; font.bold: true }
                    StoneButton { label: "YouTube access: " + bridge.cookieSource; Layout.fillWidth: true; Layout.preferredHeight: 40; onActivated: { accessPopup.returnToSettings = true; settingsPopup.close(); accessPopup.toggleFrom(this) } }
                    Text { text: "METADATA"; color: theme.accent; font.pixelSize: 13; font.bold: true }
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
                            objectName: "settingsRightColumn"
                            Layout.fillWidth: true
                            Layout.preferredWidth: 360
                            Layout.alignment: Qt.AlignTop
                            spacing: 12
                    Text { visible: window.outputFormat === "MP4"; text: "MP4 VIDEO"; color: theme.accent; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        visible: window.outputFormat === "MP4"
                        Layout.fillWidth: true
                        StoneButton {
                            id: settingsQualityButton
                            objectName: "settingsQualityButton"
                            label: "Quality: " + bridge.quality
                            Layout.fillWidth: true; Layout.preferredHeight: 40
                            onActivated: { settingsQualityMenu.anchorItem = this; settingsQualityMenu.toggleFrom(this) }
                        }
                        StoneButton {
                            id: settingsOutputModeButton
                            objectName: "settingsOutputModeButton"
                            label: "Output mode: " + bridge.exportModeLabel
                            Layout.fillWidth: true; Layout.preferredHeight: 40
                            onActivated: { settingsOutputModeMenu.anchorItem = this; settingsOutputModeMenu.toggleFrom(this) }
                        }
                    }
                    ManualMp4Settings {
                        objectName: "settingsManualMp4"
                        headingColor: theme.accent
                        visible: window.outputFormat === "MP4" && bridge.exportMode === "Manual Override"
                        Layout.fillWidth: true
                        backend: bridge
                        colors: theme
                    }
                    RowLayout {
                        visible: window.outputFormat === "MP4"
                        Layout.fillWidth: true
                        Text { text: "Translated subtitles"; color: theme.muted; font.pixelSize: 14; Layout.fillWidth: true }
                        StoneButton {
                            id: translatedSubtitleButton
                            objectName: "translatedSubtitleButton"
                            label: bridge.translatedSubtitleLabel
                            Layout.preferredWidth: 90; Layout.preferredHeight: 38
                            onActivated: { translatedSubtitleMenu.anchorItem = this; translatedSubtitleMenu.toggleFrom(this) }
                        }
                    }
                    Text {
                        visible: window.outputFormat === "MP4"
                        text: "For future downloads, save original captions and the selected provider translation when available."
                        color: theme.muted; font.pixelSize: 12; wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text { visible: window.outputFormat === "MP4"; text: "MP4 OPTIONS"; color: theme.accent; font.pixelSize: 13; font.bold: true }
                    Repeater {
                model: [
                    { key: "use_nvenc", heading: "ENCODING", label: "Use NVIDIA encoder" },
                    { key: "embed_thumbnail", heading: "EMBED IN MP4", label: "Thumbnail" },
                    { key: "embed_metadata", heading: "", label: "Metadata" },
                    { key: "write_thumbnail", heading: "SAVE ALONGSIDE MP4", label: "Thumbnail file" },
                    { key: "write_info_json", heading: "", label: "Info JSON file" }
                ]
                ColumnLayout {
                    required property var modelData
                    // NVIDIA encoding never applies on macOS; elsewhere it stays visible as Unavailable.
                    visible: window.outputFormat === "MP4" &&
                             !(modelData.key === "use_nvenc" && Qt.platform.os === "osx")
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        visible: modelData.heading.length > 0
                        text: modelData.heading
                        color: theme.accent; font.pixelSize: 12; font.bold: true
                        Layout.preferredHeight: visible ? 18 : 0
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 39
                        Text { text: modelData.label; color: theme.text; font.pixelSize: 15; Layout.fillWidth: true }
                        StoneButton {
                            enabled: modelData.key !== "use_nvenc" || bridge.nvencAvailable
                            label: !enabled ? "Unavailable" : (bridge.downloadOptions[modelData.key] ? "On" : "Off")
                            selected: enabled && bridge.downloadOptions[modelData.key]
                            Layout.preferredWidth: enabled ? 74 : 108
                            Layout.preferredHeight: 36
                            onActivated: bridge.setDownloadOption(modelData.key, !bridge.downloadOptions[modelData.key])
                        }
                    }
                }
                    }
                    Text { visible: window.outputFormat === "MP3"; text: "MP3 AUDIO"; color: theme.accent; font.pixelSize: 13; font.bold: true }
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
                            var next = choices[(choices.indexOf(bridge.mp3Values[modelData.key]) + 1) % choices.length]
                            if (modelData.key === "mp3_cover_art_mode" && next === "Custom art" && !bridge.mp3CoverAvailable)
                                mp3CoverDialog.open()
                            else
                                bridge.setMp3Value(modelData.key, next)
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
                        StoneButton { label: "Clear"; Layout.preferredWidth: 64; Layout.preferredHeight: 38; onActivated: bridge.clearMp3Cover() }
                    }
                    Text {
                        visible: window.outputFormat === "Original audio"
                        text: "ORIGINAL AUDIO"
                        color: theme.accent; font.pixelSize: 13; font.bold: true
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
                    Text { text: "APPEARANCE"; color: theme.accent; font.pixelSize: 13; font.bold: true }
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Theme"; color: theme.muted; font.pixelSize: 13 }
                        StoneButton {
                            label: bridge.appearanceTheme + "  ▾"
                            Layout.fillWidth: true; Layout.preferredHeight: 40
                            onActivated: { appearanceThemeMenu.anchorItem = this; appearanceThemeMenu.toggleFrom(this) }
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
                    Text { objectName: "settingsPrivacyHeading"; text: "PRIVACY"; color: theme.accent; font.pixelSize: 13; font.bold: true }
                    Text {
                        objectName: "settingsAnalyticsUnavailable"
                        visible: !bridge.analyticsAvailable
                        text: "Usage analytics is disabled for this session."
                        color: theme.muted
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    RowLayout {
                objectName: "settingsAnalyticsRow"
                visible: bridge.analyticsAvailable
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? 40 : 0
                Text { text: "Share usage analytics"; color: theme.text; font.pixelSize: 15; Layout.fillWidth: true }
                StoneButton {
                    objectName: "settingsAnalyticsToggle"
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
                StoneButton { label: "Support"; Layout.preferredWidth: 104; Layout.preferredHeight: 40; onActivated: { settingsPopup.close(); bridge.openSupport("feedback") } }
                StoneButton {
                    id: settingsHelpButton
                    label: "Help"
                    accessibilityLabel: "Help"
                    Layout.preferredWidth: 100; Layout.preferredHeight: 40
                    onActivated: { helpMenu.anchorItem = this; helpMenu.toggleFrom(this) }
                }
                StoneButton { label: "Check for updates"; Layout.preferredWidth: 165; Layout.preferredHeight: 40; onActivated: { settingsPopup.close(); updatePopup.toggleFrom(this); bridge.checkForUpdates() } }
                Item { Layout.fillWidth: true }
                StoneButton {
                    objectName: "settingsDoneButton"
                    label: "Done"; primary: true; Layout.preferredWidth: 86; Layout.preferredHeight: 40
                    onActivated: { if (bridge.setExtraTags(extraTagsInput.text)) settingsPopup.close() }
                }
            }
        }
    }
    AnchoredPopup {
        id: appearanceThemeMenu
        parent: window.contentItem
        scrollViewport: settingsBody
        preferAbove: true
        width: 230
        height: 260
        padding: 4
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
    StonePopup {
        id: updatePopup
        objectName: "updatePopup"
        property bool explicitDeferral: false
        readonly property bool inProgress: bridge.updateBusy || bridge.updateRestartPending
        readonly property string heading: bridge.updateRecovery ? "Update needs attention" :
            bridge.updateBusy ? (bridge.updateStage === "check" ? "Checking for updates" :
                bridge.updateStage === "downloading_repair" ? "Repairing VODForge" : "Downloading update") :
            bridge.updateRestartPending ? (bridge.updateReady ? "Waiting to restart" : "Restarting VODForge") :
            bridge.updateAvailable ? "Update available" : "VODForge updates"
        onOpened: { explicitDeferral = false; bridge.updateOfferShown() }
        onClosed: bridge.updateOfferClosed(explicitDeferral)
        Connections {
            target: bridge
            function onUpdateChanged() { if (updatePopup.visible) bridge.updateOfferShown() }
        }
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(500, window.width - 40)
        height: updateContent.implicitHeight + topPadding + bottomPadding
        padding: 22
        modal: true
        closePolicy: Popup.CloseOnEscape
        ColumnLayout {
            id: updateContent
            anchors.fill: parent
            spacing: 20
            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Image {
                    objectName: "updateAppIcon"
                    source: assetUrl + "brand/icon-180.png"
                    Layout.preferredWidth: 48
                    Layout.preferredHeight: 48
                    Layout.alignment: Qt.AlignTop
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 7
                    Text {
                        objectName: "updateHeading"
                        text: updatePopup.heading
                        color: theme.text
                        font.pixelSize: 20
                        font.bold: true
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text {
                        objectName: "updateBody"
                        text: bridge.updateRecovery ?
                            "Try Repair to download a fresh verified copy, or open the download page." :
                            bridge.updateBusy && bridge.updateStage === "check" ?
                            "Looking for the latest VODForge release." : bridge.updateStatus
                        color: theme.muted
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text {
                        visible: bridge.updateBusy && bridge.updateStage !== "check"
                        text: "VODForge will restart after verification, once active work is idle."
                        color: theme.muted
                        font.pixelSize: 13
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                }
            }
            ProgressBar {
                id: updateProgress
                objectName: "updateProgress"
                visible: bridge.updateBusy
                indeterminate: true
                Layout.fillWidth: true
                Layout.preferredHeight: 5
                padding: 0
                background: StoneField {}
                contentItem: Item {
                    clip: true
                    Rectangle {
                        width: parent.width * 0.3
                        height: parent.height
                        radius: 2.5
                        color: theme.accent
                        x: -width + (parent.width + width) * updateProgress.phase
                    }
                }
                property real phase: 0
                NumberAnimation on phase {
                    from: 0; to: 1; duration: 1300
                    loops: Animation.Infinite
                    running: updateProgress.visible
                }
                Accessible.name: "Update in progress"
            }
            RowLayout {
                objectName: "updateFooter"
                Layout.fillWidth: true
                spacing: 10
                StoneButton {
                    objectName: "updateDownloadPage"
                    visible: !updatePopup.inProgress && (bridge.updateRecovery || bridge.updateManualAvailable)
                    label: "Download page"
                    Layout.preferredWidth: 140
                    Layout.preferredHeight: 40
                    onActivated: bridge.openDownloadPage()
                }
                Item { Layout.fillWidth: true }
                StoneButton {
                    objectName: "updateDismiss"
                    label: updatePopup.inProgress ? "Hide" :
                        bridge.updateAvailable || bridge.updateManualAvailable || bridge.updateRecovery ? "Later" : "Close"
                    Layout.preferredWidth: 84
                    Layout.preferredHeight: 40
                    onActivated: {
                        updatePopup.explicitDeferral = !updatePopup.inProgress
                        updatePopup.close()
                    }
                }
                StoneButton {
                    objectName: "updatePrimary"
                    visible: !updatePopup.inProgress && !bridge.updateManualAvailable
                    label: bridge.updateRecovery ? "Repair VODForge" :
                        bridge.updateAvailable ? "Download update" : "Check again"
                    emphasized: true
                    Layout.preferredWidth: 155
                    Layout.preferredHeight: 40
                    onActivated: {
                        if (bridge.updateRecovery) bridge.repairUpdate()
                        else if (bridge.updateAvailable) bridge.downloadUpdate()
                        else bridge.checkForUpdates()
                    }
                }
            }
        }
    }
    StonePopup {
        id: accessPopup
        objectName: "youtubeAccessPopup"
        property bool returnToSettings: false
        onClosed: {
            if (returnToSettings) {
                returnToSettings = false
                Qt.callLater(function() { if (window.visible) settingsPopup.open() })
            }
        }
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(560, window.width - 40)
        height: 410
        padding: 18
        modal: true
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
    StonePopup {
        id: localConversionPopup
        objectName: "localConversionPopup"
        onClosed: localProfilePopup.close()
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(500, window.width - 40)
        height: 310
        padding: 18
        modal: true
        closePolicy: bridge.localRunning ? Popup.NoAutoClose : Popup.CloseOnEscape | Popup.CloseOnPressOutside
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Text { text: "Create video from local audio"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text { text: "Choose an MP3 and a still image. The MP4 saves to your output folder."; color: theme.muted; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                StoneField {
                    objectName: "localAudioPickerField"
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    interactive: !bridge.localRunning
                    onActivated: localAudioDialog.open()
                    Text { anchors.fill: parent; anchors.margins: 12; text: bridge.localAudio || "Choose MP3 audio"; color: theme.text; font.pixelSize: 14; elide: Text.ElideMiddle; verticalAlignment: Text.AlignVCenter }
                }
                StoneButton { label: "Browse"; Layout.preferredWidth: 85; Layout.preferredHeight: 40; enabled: !bridge.localRunning; onActivated: localAudioDialog.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                StoneField {
                    objectName: "localImagePickerField"
                    Layout.fillWidth: true; Layout.preferredHeight: 42
                    interactive: !bridge.localRunning
                    onActivated: localImageDialog.open()
                    Text { anchors.fill: parent; anchors.margins: 12; text: bridge.localImage || "Choose still image"; color: theme.text; font.pixelSize: 14; elide: Text.ElideMiddle; verticalAlignment: Text.AlignVCenter }
                }
                StoneButton { label: "Browse"; Layout.preferredWidth: 85; Layout.preferredHeight: 40; enabled: !bridge.localRunning; onActivated: localImageDialog.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                Text { text: "Profile"; color: theme.muted; font.pixelSize: 14 }
                Item { Layout.fillWidth: true }
                StoneButton { label: bridge.localProfile + "  ▾"; Layout.preferredWidth: 295; Layout.preferredHeight: 38; enabled: !bridge.localRunning; onActivated: { localProfilePopup.anchorItem = this; localProfilePopup.toggleFrom(this) } }
            }
            Text { text: bridge.localProgress || bridge.status; color: theme.muted; font.pixelSize: 14; elide: Text.ElideRight; Layout.fillWidth: true }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Layout.rightMargin: 12
                Layout.bottomMargin: 8
                Item { Layout.fillWidth: true }
                StoneButton { label: "Close"; Layout.preferredWidth: 82; Layout.preferredHeight: 40; enabled: !bridge.localRunning; onActivated: localConversionPopup.close() }
                StoneButton { label: bridge.localRunning ? "Stop" : "Create MP4"; emphasized: !bridge.localRunning; Layout.preferredWidth: 110; Layout.preferredHeight: 40; onActivated: bridge.localRunning ? bridge.cancelLocalConversion() : bridge.startLocalConversion() }
            }
        }
    }
    AnchoredPopup {
        id: localProfilePopup
        parent: window.contentItem
        preferAbove: true
        width: 320
        height: 184
        padding: 3
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
    AnchoredPopup {
        id: formatMenu
        objectName: "forgeFormatPopup"
        parent: window.contentItem
        width: 170
        height: 150
        padding: 3
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
    StonePopup {
        id: optionsMenu
        objectName: "optionsMenu"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        property real customReveal: bridge.exportMode === "Manual Override" ? 1 : 0
        Behavior on customReveal {
            NumberAnimation { duration: bridge.reducedMotion ? 0 : 280; easing.type: Easing.InOutCubic }
        }
        readonly property real baseWidth: Math.min(550, window.width - 40)
        readonly property real expandedWidth: Math.min(baseWidth + (baseWidth - 32) / 2 + 16, window.width - 40)
        width: baseWidth + (expandedWidth - baseWidth) * customReveal
        readonly property real customColumnWidth: (expandedWidth - 48) / 3
        height: Math.min(window.height - 40, 540, 387 + Math.max(0, Math.max(composerManualControls.implicitHeight, composerOptionsContent.implicitHeight) + 48 - 387) * customReveal)
        padding: 8
        topPadding: 40
        StoneButton {
            objectName: "composerOptionsCloseButton"
            x: optionsMenu.availableWidth - width
            y: -32
            width: 28; height: 28
            label: "×"
            accessibilityLabel: "Close options"
            onActivated: optionsMenu.close()
        }
        modal: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: "#9915151c" }
        Item {
            id: customOptionsColumn
            objectName: "customOptionsColumn"
            width: optionsMenu.customColumnWidth * optionsMenu.customReveal
            height: optionsMenu.availableHeight
            clip: true
            visible: optionsMenu.customReveal > 0
            opacity: optionsMenu.customReveal
            ScrollView {
                objectName: "composerManualScroll"
                contentWidth: availableWidth
                anchors.fill: parent
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ManualMp4Settings {
                    id: composerManualControls
                    objectName: "composerManualMp4"
                    width: optionsMenu.customColumnWidth
                    gridColumns: 1
                    backend: bridge
                    colors: theme
                    headingColor: theme.accent
                }
            }
        }
        ScrollView {
            id: composerOptionsScroll
            x: customOptionsColumn.width + 16 * optionsMenu.customReveal
            width: optionsMenu.availableWidth - x
            height: optionsMenu.availableHeight
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                id: composerOptionsContent
                width: composerOptionsScroll.availableWidth
                spacing: 12
        Row {
            width: parent.width
            height: 339
            spacing: 16
            Column {
                width: (parent.width - 16) / 2
                spacing: 3
                Text { text: "OUTPUT MODE"; color: theme.accent; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1; height: 32; leftPadding: 8; verticalAlignment: Text.AlignVCenter }
                Repeater {
                    model: bridge.exportModeOptions
                    StoneButton {
                        required property var modelData
                        width: parent.width; height: 40
                        label: modelData.label
                        selected: bridge.exportMode === modelData.value
                        onActivated: {
                            bridge.setExportMode(modelData.value)
                        }
                    }
                }
                Text {
                    width: parent.width
                    height: 40
                    text: "Custom reveals the manual MP4 controls."
                    color: theme.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    verticalAlignment: Text.AlignVCenter
                }
            }
            Column {
                width: (parent.width - 16) / 2
                spacing: 3
                Text { text: "QUALITY"; color: theme.accent; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1; height: 32; leftPadding: 8; verticalAlignment: Text.AlignVCenter }
                Repeater {
                    model: qualityOptions
                    StoneButton {
                        required property string modelData
                        width: parent.width; height: 40
                        label: modelData
                        selected: bridge.quality === modelData
                        onActivated: bridge.setQuality(modelData)
                    }
                }
            }
        }
                Column {
                    objectName: "composerCustomSummary"
                    visible: optionsMenu.customReveal > 0
                    opacity: optionsMenu.customReveal
                    width: parent.width
                    spacing: 10
                    Rectangle { width: parent.width; height: 1; color: theme.border }
                    Text { text: "YOUR CUSTOM OUTPUT"; color: theme.accent; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1 }
                    Text {
                        objectName: "composerCustomSummaryValues"
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: theme.text
                        font.pixelSize: 14
                        text: bridge.quality + "  •  " + (bridge.manualValues.manual_rate_control === "Quality"
                            ? "CRF " + bridge.manualValues.manual_crf
                            : bridge.manualValues.manual_video_bitrate + " kbps video") + "\n"
                            + bridge.manualValues.manual_audio_codec + "  •  " + bridge.manualValues.manual_audio_bitrate
                            + " kbps  •  " + bridge.manualValues.manual_channels + "\n"
                            + "Encoding speed: " + bridge.manualValues.manual_preset
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: theme.muted
                        font.pixelSize: 13
                        text: bridge.manualValues.manual_rate_control === "Quality"
                            ? "Quality adjusts the bitrate to the picture. A lower CRF keeps more detail and usually makes a larger file."
                            : "CBR targets your chosen video bitrate. Raise it to preserve more detail, or lower it for smaller files."
                    }
                    Text {
                        width: parent.width
                        wrapMode: Text.WordWrap
                        color: theme.muted
                        font.pixelSize: 12
                        text: "Resolution is limited by the source. Slower encoding can improve compression but takes longer."
                    }
                }
            }
        }
    }
    AnchoredPopup {
        id: settingsOutputModeMenu
        objectName: "settingsOutputModeMenu"
        parent: window.contentItem
        scrollViewport: settingsBody
        width: 250
        height: bridge.exportModeOptions.length * 41 + 8
        padding: 4
        onOpened: settingsQualityMenu.close()
        Column {
            anchors.fill: parent
            spacing: 1
            Repeater {
                model: bridge.exportModeOptions
                StoneButton {
                    required property var modelData
                    width: parent.width; height: 40
                    label: modelData.label
                    selected: bridge.exportMode === modelData.value
                    onActivated: { bridge.setExportMode(modelData.value); settingsOutputModeMenu.close() }
                }
            }
        }
    }
    AnchoredPopup {
        id: settingsQualityMenu
        objectName: "settingsQualityMenu"
        parent: window.contentItem
        scrollViewport: settingsBody
        width: 250
        height: qualityOptions.length * 41 + 8
        padding: 4
        onOpened: settingsOutputModeMenu.close()
        Column {
            anchors.fill: parent
            spacing: 1
            Repeater {
                model: qualityOptions
                StoneButton {
                    required property string modelData
                    width: parent.width; height: 40
                    label: modelData
                    selected: bridge.quality === modelData
                    onActivated: { bridge.setQuality(modelData); settingsQualityMenu.close() }
                }
            }
        }
    }
    AnchoredPopup {
        id: translatedSubtitleMenu
        objectName: "translatedSubtitleMenu"
        parent: window.contentItem
        scrollViewport: settingsBody
        width: 270; height: Math.min(320, window.height - 48)
        padding: 4
        ScrollView {
            anchors.fill: parent
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            Column {
                width: parent.width
                spacing: 1
                Repeater {
                    model: bridge.subtitleLanguageChoices
                    StoneButton {
                        required property var modelData
                        width: parent.width; height: 40
                        label: modelData.label
                        selected: bridge.translatedSubtitleLanguage === modelData.code
                        onActivated: { bridge.setTranslatedSubtitleLanguage(modelData.code); translatedSubtitleMenu.close() }
                    }
                }
            }
        }
    }

}
