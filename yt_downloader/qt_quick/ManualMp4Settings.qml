import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: manual
    required property var backend
    required property var colors
    property int gridColumns: 2
    property color headingColor: manual.colors.muted
    spacing: 7

    Text { objectName: "manualMp4Heading"; text: "MANUAL MP4"; color: manual.headingColor; font.pixelSize: 13; font.bold: true }
    GridLayout {
        Layout.minimumWidth: 0; Layout.fillWidth: true
        columns: manual.gridColumns
        columnSpacing: 16
        rowSpacing: 7

        ColumnLayout {
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Video rate control"; color: manual.colors.muted; font.pixelSize: 13 }
            InlineSelector {
                objectName: "manualRateControlSelector"
                buttonObjectName: "manualRateControlButton"
                Layout.minimumWidth: 0; Layout.fillWidth: true
                currentValue: manual.backend.manualValues.manual_rate_control
                buttonText: currentValue
                options: [{label: "CBR", value: "CBR"}, {label: "Quality", value: "Quality"}]
                onChosen: value => manual.backend.setManualValue("manual_rate_control", value)
            }
        }
        ColumnLayout {
            objectName: "manualCrfGroup"
            visible: manual.backend.manualValues.manual_rate_control === "Quality"
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Video quality (CRF, 1–51)"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneField {
                Layout.minimumWidth: 0; Layout.fillWidth: true; Layout.preferredHeight: 40
                TextField {
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                    padding: 0; verticalAlignment: TextInput.AlignVCenter; font.pixelSize: 15
                    text: manual.backend.manualValues.manual_crf
                    enabled: manual.backend.manualValues.manual_rate_control === "Quality"
                    color: manual.colors.text; background: Item {}
                    onEditingFinished: manual.backend.setManualValue("manual_crf", text)
                }
            }
        }
        ColumnLayout {
            objectName: "manualCbrGroup"
            visible: manual.backend.manualValues.manual_rate_control === "CBR"
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "CBR video bitrate (kbps)"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneField {
                Layout.minimumWidth: 0; Layout.fillWidth: true; Layout.preferredHeight: 40
                TextField {
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                    padding: 0; verticalAlignment: TextInput.AlignVCenter; font.pixelSize: 15
                    text: manual.backend.manualValues.manual_video_bitrate
                    enabled: manual.backend.manualValues.manual_rate_control === "CBR"
                    color: manual.colors.text; background: Item {}
                    onEditingFinished: manual.backend.setManualValue("manual_video_bitrate", text)
                }
            }
        }
        ColumnLayout {
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Audio bitrate (kbps)"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneField {
                Layout.minimumWidth: 0; Layout.fillWidth: true; Layout.preferredHeight: 40
                TextField {
                    anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 14
                    padding: 0; verticalAlignment: TextInput.AlignVCenter; font.pixelSize: 15
                    text: manual.backend.manualValues.manual_audio_bitrate
                    color: manual.colors.text; background: Item {}
                    onEditingFinished: manual.backend.setManualValue("manual_audio_bitrate", text)
                }
            }
        }
        ColumnLayout {
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Audio codec"; color: manual.colors.muted; font.pixelSize: 13 }
            InlineSelector {
                objectName: "manualAudioCodecSelector"
                buttonObjectName: "manualAudioCodecButton"
                Layout.minimumWidth: 0; Layout.fillWidth: true
                currentValue: manual.backend.manualValues.manual_audio_codec
                buttonText: currentValue
                options: [{label: "AAC", value: "AAC"}, {label: "MP3", value: "MP3"}]
                onChosen: value => manual.backend.setManualValue("manual_audio_codec", value)
            }
        }
        ColumnLayout {
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Sample rate"; color: manual.colors.muted; font.pixelSize: 13 }
            InlineSelector {
                objectName: "manualSampleRateSelector"
                buttonObjectName: "manualSampleRateButton"
                Layout.minimumWidth: 0; Layout.fillWidth: true
                currentValue: manual.backend.manualValues.manual_sample_rate
                buttonText: currentValue === "48000" ? "48 kHz" : "44.1 kHz"
                options: [{label: "48 kHz", value: "48000"}, {label: "44.1 kHz", value: "44100"}]
                onChosen: value => manual.backend.setManualValue("manual_sample_rate", value)
            }
        }
        ColumnLayout {
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Channels"; color: manual.colors.muted; font.pixelSize: 13 }
            InlineSelector {
                objectName: "manualChannelsSelector"
                buttonObjectName: "manualChannelsButton"
                Layout.minimumWidth: 0; Layout.fillWidth: true
                currentValue: manual.backend.manualValues.manual_channels
                buttonText: currentValue
                options: [{label: "Stereo", value: "Stereo"}, {label: "Mono", value: "Mono"}]
                onChosen: value => manual.backend.setManualValue("manual_channels", value)
            }
        }
        ColumnLayout {
            Layout.minimumWidth: 0; Layout.fillWidth: true
            Text { Layout.fillWidth: true; wrapMode: Text.WordWrap; text: "Encoding speed"; color: manual.colors.muted; font.pixelSize: 13 }
            InlineSelector {
                objectName: "manualPresetSelector"
                buttonObjectName: "manualPresetButton"
                Layout.minimumWidth: 0; Layout.fillWidth: true
                currentValue: manual.backend.manualValues.manual_preset
                buttonText: currentValue
                options: [
                    {label: "ultrafast", value: "ultrafast"},
                    {label: "veryfast", value: "veryfast"},
                    {label: "fast", value: "fast"},
                    {label: "medium", value: "medium"},
                    {label: "slow", value: "slow"}
                ]
                onChosen: value => manual.backend.setManualValue("manual_preset", value)
            }
        }
    }
}
