import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: manual
    required property var backend
    required property var colors
    spacing: 7

    Text { text: "MANUAL MP4"; color: manual.colors.muted; font.pixelSize: 13; font.bold: true }
    GridLayout {
        Layout.fillWidth: true
        columns: 2
        columnSpacing: 16
        rowSpacing: 7

        ColumnLayout {
            Layout.fillWidth: true
            Text { text: "Video rate control"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneButton {
                label: manual.backend.manualValues.manual_rate_control + "  ▾"
                Layout.fillWidth: true; Layout.preferredHeight: 39
                onActivated: manual.backend.setManualValue("manual_rate_control", manual.backend.manualValues.manual_rate_control === "CBR" ? "Quality" : "CBR")
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Text { text: "Video quality (CRF, 1–51)"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneField {
                Layout.fillWidth: true; Layout.preferredHeight: 40
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
            Layout.fillWidth: true
            Text { text: "CBR video bitrate (kbps)"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneField {
                Layout.fillWidth: true; Layout.preferredHeight: 40
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
            Layout.fillWidth: true
            Text { text: "Audio bitrate (kbps)"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneField {
                Layout.fillWidth: true; Layout.preferredHeight: 40
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
            Layout.fillWidth: true
            Text { text: "Audio codec"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneButton {
                label: manual.backend.manualValues.manual_audio_codec + "  ▾"
                Layout.fillWidth: true; Layout.preferredHeight: 39
                onActivated: manual.backend.setManualValue("manual_audio_codec", manual.backend.manualValues.manual_audio_codec === "AAC" ? "MP3" : "AAC")
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Text { text: "Sample rate"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneButton {
                label: manual.backend.manualValues.manual_sample_rate === "48000" ? "48 kHz" : "44.1 kHz"
                Layout.fillWidth: true; Layout.preferredHeight: 39
                onActivated: manual.backend.setManualValue("manual_sample_rate", manual.backend.manualValues.manual_sample_rate === "48000" ? "44100" : "48000")
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Text { text: "Channels"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneButton {
                label: manual.backend.manualValues.manual_channels + "  ▾"
                Layout.fillWidth: true; Layout.preferredHeight: 39
                onActivated: manual.backend.setManualValue("manual_channels", manual.backend.manualValues.manual_channels === "Stereo" ? "Mono" : "Stereo")
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Text { text: "Encoding speed"; color: manual.colors.muted; font.pixelSize: 13 }
            StoneButton {
                label: manual.backend.manualValues.manual_preset + "  ▾"
                Layout.fillWidth: true; Layout.preferredHeight: 39
                onActivated: {
                    const choices = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"]
                    const current = choices.indexOf(manual.backend.manualValues.manual_preset)
                    manual.backend.setManualValue("manual_preset", choices[(current + 1) % choices.length])
                }
            }
        }
    }
}
