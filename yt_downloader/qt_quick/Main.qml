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

    MediaPlayer {
        id: mediaPlayer
        objectName: "watchMediaPlayer"
        audioOutput: AudioOutput { id: audioOutput; volume: 0.8 }
        videoOutput: videoSurface
        function reportProgress() {
            var status = "Ready"
            if (error !== MediaPlayer.NoError) status = "Failed"
            else if (mediaStatus === MediaPlayer.EndOfMedia) status = "Ended"
            else if (playbackState === MediaPlayer.PlayingState) status = "Playing"
            else if (playbackState === MediaPlayer.PausedState) status = "Paused"
            bridge.observePlayback(position / 1000, duration / 1000, status)
        }
        onPositionChanged: reportProgress()
        onDurationChanged: reportProgress()
        onPlaybackStateChanged: reportProgress()
        onMediaStatusChanged: reportProgress()
        onErrorChanged: reportProgress()
    }
    Connections {
        target: bridge
        function onSourceAccepted() { urlInput.text = "" }
        function onPlaybackRequested() {
            mediaPlayer.stop()
            mediaPlayer.source = ""
            mediaPlayer.source = bridge.playbackUrl
            mediaPlayer.play()
        }
        function onPlaybackSeekRequested(position) {
            mediaPlayer.setPosition(position * 1000)
        }
    }
    FolderDialog {
        id: outputFolderDialog
        title: "Choose output folder"
        onAccepted: bridge.chooseOutputUrl(selectedFolder)
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

    Image {
        id: artwork
        objectName: "fullCoverArtwork"
        anchors.fill: parent
        source: "image://vodforge/backdrop"
        fillMode: Image.PreserveAspectCrop
        smooth: true
        cache: true
    }

    property int gutter: width < 960 ? 22 : 38
    property int rowGap: 14
    property string outputFormat: bridge.outputFormat

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: window.gutter
        spacing: window.rowGap

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 52
            spacing: 10
            Text {
                text: "VF  VODForge"
                color: theme.text
                font.family: "Arial"
                font.pixelSize: 22
                font.bold: true
                Layout.preferredWidth: window.width < 960 ? 158 : 198
            }
            Repeater {
                model: ["Forge", "Library", "Watch", "Activity"]
                StoneButton {
                    required property string modelData
                    label: modelData
                    selected: bridge.selection === modelData
                    icon: "image://vodforge/icon/" + (
                        modelData === "Forge" ? "download-20.png" :
                        modelData === "Library" ? "folder-20.png" :
                        modelData === "Watch" ? "play.png" : "activity-20.png")
                    Layout.preferredWidth: window.width < 960 ? 93 : 108
                    Layout.preferredHeight: 40
                    onActivated: bridge.select(modelData)
                }
            }
            Item { Layout.fillWidth: true }
            StoneField {
                Layout.preferredWidth: window.width < 960 ? 150 : 220
                Layout.preferredHeight: 40
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
                label: "⚙"
                Layout.preferredWidth: 46
                Layout.preferredHeight: 40
                onActivated: settingsPopup.open()
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
                Layout.preferredHeight: 48
                spacing: 10
                StoneButton {
                    label: bridge.running ? "Stop" : "Ready"
                    Layout.preferredWidth: 128
                    Layout.preferredHeight: 42
                    enabled: bridge.running
                    onActivated: bridge.cancel()
                }
                Text {
                    text: "Save to"
                    color: theme.muted
                    font.pixelSize: 15
                    Layout.leftMargin: 10
                }
                StoneField {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    focused: pathInput.activeFocus
                    TextField {
                        id: pathInput
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 10
                        text: bridge.outputPath
                        color: theme.text
                        background: Item {}
                        font.pixelSize: 15
                        onAccepted: bridge.setOutputPath(text)
                    }
                }
                StoneButton {
                    label: "Browse"
                    Layout.preferredWidth: 86
                    Layout.preferredHeight: 42
                    onActivated: outputFolderDialog.open()
                }
                StoneButton {
                    label: bridge.batchSummary === "No URL list loaded" ? "Load URL list" : "List loaded"
                    Layout.preferredWidth: 111
                    Layout.preferredHeight: 42
                    onActivated: urlListDialog.open()
                }
                StoneButton {
                    visible: bridge.batchSummary !== "No URL list loaded"
                    label: "Clear"
                    Layout.preferredWidth: 57
                    Layout.preferredHeight: 42
                    onActivated: bridge.clearBatchList()
                }
                StoneButton {
                    label: "Create video"
                    Layout.preferredWidth: 132
                    Layout.preferredHeight: 42
                    onActivated: localConversionPopup.open()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 128
                Layout.topMargin: 16
                spacing: 28
                Image {
                    source: assetUrl + "brand/icon-180.png"
                    Layout.preferredWidth: 68
                    Layout.preferredHeight: 68
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
                ColumnLayout {
                    spacing: 7
                    Text {
                        text: bridge.running ? "Download in progress" : "Ready for a new run"
                        color: theme.text
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        text: "Paste a video URL above, then press Return to begin."
                        color: theme.muted
                        font.pixelSize: 15
                    }
                    Text {
                        text: bridge.quality + "  ·  " + bridge.exportMode
                        color: theme.muted
                        font.pixelSize: 15
                    }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: Math.round(bridge.progress) + "%"
                    color: theme.selection
                    font.pixelSize: 34
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: theme.border
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 185
                spacing: 24
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 18
                    Text { text: bridge.status; color: theme.muted; font.pixelSize: 15 }
                    Text {
                        visible: bridge.batchSummary !== "No URL list loaded"
                        text: bridge.batchSummary
                        color: theme.muted
                        font.pixelSize: 14
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                    Text {
                        text: bridge.running ? "◌   Processing your media…" : "◌   Your next run’s progress will appear here."
                        color: theme.muted
                        font.pixelSize: 17
                    }
                    Item { Layout.fillHeight: true }
                }
                ColumnLayout {
                    Layout.preferredWidth: Math.min(315, window.width * 0.28)
                    Layout.fillHeight: true
                    spacing: 11
                    Text {
                        text: "Output: " + window.outputFormat + " · " + bridge.exportMode
                        color: theme.muted
                        font.pixelSize: 14
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Text { text: "Format             " + window.outputFormat; color: theme.muted; font.pixelSize: 14 }
                    Text {
                        text: "Video               " + (window.outputFormat === "MP4" ? "H.264" : "None")
                        color: theme.muted
                        font.pixelSize: 14
                    }
                    Text {
                        text: "Audio               " + (window.outputFormat === "MP3" ? "MP3" :
                              window.outputFormat === "Original audio" ? "Source" :
                              bridge.exportMode === "Manual Override" ? bridge.manualValues.manual_audio_codec : "AAC")
                        color: theme.muted
                        font.pixelSize: 14
                    }
                    Text { text: "Output mode     " + bridge.exportMode; color: theme.muted; font.pixelSize: 14 }
                    Item { Layout.fillHeight: true }
                }
            }

            Item { Layout.fillHeight: true }

            StoneField {
                Layout.fillWidth: true
                Layout.preferredHeight: 74
                Column {
                    anchors.fill: parent
                    anchors.margins: 17
                    spacing: 8
                    Text { text: "Recent downloads"; color: theme.text; font.pixelSize: 16; font.bold: true }
                    Text { text: bridge.history.length + " saved item(s) in Library"; color: theme.muted; font.pixelSize: 14 }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 23
                Text { text: bridge.running ? "Run active" : "No active run"; color: theme.muted; font.pixelSize: 14 }
                Item { Layout.fillWidth: true }
                Text { text: "Runs process one at a time"; color: theme.muted; font.pixelSize: 14 }
            }
        }

        Item {
            visible: bridge.selection === "Library"
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                spacing: 16
                Text { text: "Library"; color: theme.text; font.pixelSize: 26; font.bold: true }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: bridge.history.length + " matching item(s)"; color: theme.muted; font.pixelSize: 15 }
                    Item { Layout.fillWidth: true }
                    Repeater {
                        model: ["All", "MP4", "MP3", "Original audio"]
                        StoneButton {
                            required property string modelData
                            label: modelData === "All" ? "All media" : modelData
                            selected: bridge.libraryType === modelData
                            Layout.preferredWidth: modelData === "Original audio" ? 130 : 96
                            Layout.preferredHeight: 38
                            onActivated: bridge.setLibraryType(modelData)
                        }
                    }
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: bridge.history
                    spacing: 9
                    clip: true
                    delegate: StoneField {
                        required property var modelData
                        required property int index
                        width: ListView.view.width
                        height: 67
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 13
                            spacing: 10
                            ColumnLayout {
                                Layout.fillWidth: true
                                Text { text: modelData.title; color: theme.text; font.pixelSize: 17; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text { text: modelData.type; color: theme.muted; font.pixelSize: 13 }
                            }
                            StoneButton {
                                label: "Play"
                                Layout.preferredWidth: 72
                                Layout.preferredHeight: 38
                                onActivated: bridge.openLibraryItem(modelData.sourceIndex)
                            }
                        }
                    }
                }
            }
        }
        Item {
            visible: bridge.selection === "Watch"
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                spacing: 12
                Text { text: "Watch"; color: theme.text; font.pixelSize: 26; font.bold: true }
                VideoOutput {
                    id: videoSurface
                    objectName: "watchVideoSurface"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    fillMode: VideoOutput.PreserveAspectFit
                }
                Text {
                    text: mediaPlayer.errorString.length ? mediaPlayer.errorString :
                          bridge.playbackUrl.toString().length ? "" : "Choose an item in Library to play."
                    color: theme.muted
                    font.pixelSize: 15
                }
                Slider {
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(1, mediaPlayer.duration)
                    value: mediaPlayer.position
                    onMoved: {
                        bridge.manualPlaybackSeek(value / 1000)
                        mediaPlayer.setPosition(value)
                    }
                    background: StoneField { x: 0; y: parent.height / 2 - 5; width: parent.width; height: 10 }
                    handle: StoneButton { x: parent.visualPosition * (parent.width - width); y: parent.height / 2 - height / 2; width: 22; height: 22; label: ""; interactive: false; transientMaterial: false }
                }
                RowLayout {
                    Layout.fillWidth: true
                    StoneButton {
                        label: mediaPlayer.playbackState === MediaPlayer.PlayingState ? "Pause" : "Play"
                        transientMaterial: false
                        Layout.preferredWidth: 95
                        Layout.preferredHeight: 40
                        onActivated: mediaPlayer.playbackState === MediaPlayer.PlayingState ? mediaPlayer.pause() : mediaPlayer.play()
                    }
                    Text { text: Math.floor(mediaPlayer.position / 1000) + "s / " + Math.floor(mediaPlayer.duration / 1000) + "s"; color: theme.muted; font.pixelSize: 14 }
                    Item { Layout.fillWidth: true }
                    Text { text: "Volume"; color: theme.muted; font.pixelSize: 14 }
                    Slider {
                        Layout.preferredWidth: 160
                        from: 0; to: 1; value: audioOutput.volume
                        onMoved: audioOutput.volume = value
                        background: StoneField { x: 0; y: parent.height / 2 - 5; width: parent.width; height: 10 }
                        handle: StoneButton { x: parent.visualPosition * (parent.width - width); y: parent.height / 2 - height / 2; width: 22; height: 22; label: ""; interactive: false; transientMaterial: false }
                    }
                }
            }
        }
        Item {
            visible: bridge.selection === "Activity"
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                spacing: 16
                Text { text: "Activity"; color: theme.text; font.pixelSize: 26; font.bold: true }
                Text { text: bridge.activity.length + " recent run(s)"; color: theme.muted; font.pixelSize: 15 }
                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: bridge.activity
                    spacing: 9
                    clip: true
                    delegate: StoneField {
                        required property var modelData
                        width: ListView.view.width
                        height: 82
                        Column {
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 5
                            Text { text: modelData.title + "  ·  " + modelData.status; color: theme.text; font.pixelSize: 16; elide: Text.ElideRight; width: parent.width }
                            Text { text: modelData.detail; color: theme.muted; font.pixelSize: 13; elide: Text.ElideRight; width: parent.width }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: manualOptionsPopup
        objectName: "manualOptionsPopup"
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(650, window.width - 40)
        height: 482
        padding: 18
        modal: true
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 10 }
        ColumnLayout {
            anchors.fill: parent
            spacing: 9
            Text { text: "Manual MP4 settings"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text { text: "Review the codec and rate settings before a Manual Override run."; color: theme.muted; font.pixelSize: 14 }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 16
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 6
                    Text { text: "Rate control"; color: theme.muted; font.pixelSize: 13 }
                    StoneButton { label: bridge.manualValues.manual_rate_control; Layout.fillWidth: true; Layout.preferredHeight: 39; onActivated: bridge.setManualValue("manual_rate_control", bridge.manualValues.manual_rate_control === "CBR" ? "Quality" : "CBR") }
                    Text { text: "Video bitrate (kbps)"; color: theme.muted; font.pixelSize: 13 }
                    StoneField {
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        TextField { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; padding: 0; verticalAlignment: TextInput.AlignVCenter; font.pixelSize: 15; text: bridge.manualValues.manual_video_bitrate; enabled: bridge.manualValues.manual_rate_control === "CBR"; color: theme.text; background: Item {} onEditingFinished: bridge.setManualValue("manual_video_bitrate", text) }
                    }
                    Text { text: "Quality CRF"; color: theme.muted; font.pixelSize: 13 }
                    StoneField {
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        TextField { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; padding: 0; verticalAlignment: TextInput.AlignVCenter; font.pixelSize: 15; text: bridge.manualValues.manual_crf; enabled: bridge.manualValues.manual_rate_control === "Quality"; color: theme.text; background: Item {} onEditingFinished: bridge.setManualValue("manual_crf", text) }
                    }
                    Text { text: "x264 preset"; color: theme.muted; font.pixelSize: 13 }
                    StoneButton {
                        label: bridge.manualValues.manual_preset + "  ▾"; Layout.fillWidth: true; Layout.preferredHeight: 39
                        onActivated: {
                            var choices = ["ultrafast", "veryfast", "fast", "medium", "slow"]
                            bridge.setManualValue("manual_preset", choices[(choices.indexOf(bridge.manualValues.manual_preset) + 1) % choices.length])
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 6
                    Text { text: "Audio bitrate (kbps)"; color: theme.muted; font.pixelSize: 13 }
                    StoneField {
                        Layout.fillWidth: true; Layout.preferredHeight: 40
                        TextField { anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14; padding: 0; verticalAlignment: TextInput.AlignVCenter; font.pixelSize: 15; text: bridge.manualValues.manual_audio_bitrate; color: theme.text; background: Item {} onEditingFinished: bridge.setManualValue("manual_audio_bitrate", text) }
                    }
                    Text { text: "Audio codec"; color: theme.muted; font.pixelSize: 13 }
                    StoneButton { label: bridge.manualValues.manual_audio_codec; Layout.fillWidth: true; Layout.preferredHeight: 39; onActivated: bridge.setManualValue("manual_audio_codec", bridge.manualValues.manual_audio_codec === "AAC" ? "MP3" : "AAC") }
                    Text { text: "Audio sample rate"; color: theme.muted; font.pixelSize: 13 }
                    StoneButton { label: bridge.manualValues.manual_sample_rate === "48000" ? "48 kHz" : "44.1 kHz"; Layout.fillWidth: true; Layout.preferredHeight: 39; onActivated: bridge.setManualValue("manual_sample_rate", bridge.manualValues.manual_sample_rate === "48000" ? "44100" : "48000") }
                    Text { text: "Audio channels"; color: theme.muted; font.pixelSize: 13 }
                    StoneButton { label: bridge.manualValues.manual_channels; Layout.fillWidth: true; Layout.preferredHeight: 39; onActivated: bridge.setManualValue("manual_channels", bridge.manualValues.manual_channels === "Stereo" ? "Mono" : "Stereo") }
                }
            }
            Text { text: bridge.status; color: theme.muted; font.pixelSize: 13; elide: Text.ElideRight; Layout.fillWidth: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Done"; Layout.preferredWidth: 84; Layout.preferredHeight: 40; onActivated: manualOptionsPopup.close() }
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
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 10 }
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
        x: Math.max(0, (window.width - width) / 2)
        y: Math.max(0, (window.height - height) / 2)
        width: Math.min(540, window.width - 40)
        height: 445
        padding: 18
        modal: true
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 10 }
        ColumnLayout {
            anchors.fill: parent
            spacing: 7
            Text { text: "Download settings"; color: theme.text; font.pixelSize: 21; font.bold: true }
            Text { text: "These choices apply to new Forge runs."; color: theme.muted; font.pixelSize: 14 }
            Repeater {
                model: [
                    { key: "single_video_only", label: "Single video only" },
                    { key: "use_nvenc", label: "Use NVIDIA encoder for MP4" },
                    { key: "embed_thumbnail", label: "Embed thumbnail in MP4" },
                    { key: "write_thumbnail", label: "Save thumbnail beside MP4" },
                    { key: "embed_metadata", label: "Embed metadata in MP4" },
                    { key: "write_info_json", label: "Save info JSON beside MP4" }
                ]
                RowLayout {
                    required property var modelData
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
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                StoneButton { label: "Done"; Layout.preferredWidth: 86; Layout.preferredHeight: 40; onActivated: settingsPopup.close() }
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
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 10 }
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
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 8 }
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
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 8 }
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
        background: Rectangle { color: theme.bg; border.color: theme.border; radius: 8 }
        Row {
            anchors.fill: parent
            spacing: 8
            Column {
                width: (parent.width - 8) / 2
                spacing: 3
                Text { text: "Output mode"; color: theme.muted; font.pixelSize: 13; height: 25 }
                Repeater {
                    model: ["Everyday", "Streaming", "Editing", "Sharing", "Auto CBR", "Strict Compliance", "Manual Override"]
                    StoneButton {
                        required property string modelData
                        width: parent.width; height: 40
                        label: modelData
                        selected: bridge.exportMode === modelData
                        onActivated: {
                            bridge.setExportMode(modelData)
                            optionsMenu.close()
                            if (modelData === "Manual Override") manualOptionsPopup.open()
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
