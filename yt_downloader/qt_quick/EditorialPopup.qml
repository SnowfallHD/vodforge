import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

StonePopup {
    id: editorial
    objectName: "editorialPopup"
    property var slides: []
    property string heading: "What’s new"
    property string finishLabel: "Done"
    property int index: 0
    property bool completed: false
    property bool reducedMotion: false
    property bool showSocialInvitation: false
    signal socialFollowRequested()
    readonly property bool hasRecording: !!current.recording
    readonly property var current: slides.length ? slides[Math.max(0, Math.min(index, slides.length - 1))] : ({})
    signal acknowledged(bool tryIt)
    function finish(tryIt) {
        editorial.completed = true
        editorial.acknowledged(tryIt)
        editorial.close()
    }
    onOpened: { index = 0; completed = false }
    onClosed: { if (!completed) editorial.acknowledged(false) }
    width: Math.min(showSocialInvitation ? 620 : 490, parent.width - 40)
    height: Math.min(showSocialInvitation ? 510 : hasRecording ? 550 : 470, parent.height - 40)
    x: Math.max(0, (parent.width - width) / 2)
    y: Math.max(0, (parent.height - height) / 2)
    padding: 20
    modal: true
    closePolicy: Popup.CloseOnEscape

    ColumnLayout {
        visible: !editorial.showSocialInvitation
        anchors.fill: parent
        spacing: 11
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            Item { Layout.preferredWidth: 34; Layout.preferredHeight: 34 }
            Item {
                objectName: "editorialHeadingRegion"
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                Row {
                    anchors.centerIn: parent
                    spacing: 0
                    Text {
                        text: editorial.heading.indexOf("VODForge") >= 0 ?
                              editorial.heading.split("VODForge")[0] + "VOD" : editorial.heading
                        color: theme.accent; font.pixelSize: 15; font.bold: true
                    }
                    Text {
                        visible: editorial.heading.indexOf("VODForge") >= 0
                        text: "Forge"
                        color: theme.text; font.pixelSize: 15; font.bold: true
                    }
                }
            }
            StoneButton {
                label: "×"; accessibilityLabel: "Close tour"
                size: "inline"; Layout.preferredWidth: 34
                onActivated: editorial.finish(false)
            }
        }
        Item {
            objectName: "editorialPreviewRegion"
            Layout.fillWidth: true
            Layout.fillHeight: true
            RecordedFeaturePreview {
                anchors.fill: parent
                visible: editorial.hasRecording
                active: editorial.visible && editorial.hasRecording
                reducedMotion: editorial.reducedMotion
                recordingSource: editorial.hasRecording ? assetUrl + "whats-new/" + editorial.current.recording : ""
                posterSource: editorial.current.poster ? assetUrl + "whats-new/" + editorial.current.poster : ""
                description: editorial.current.description || ""
            }
            FeaturePreview {
                visible: !editorial.hasRecording
                previewKey: editorial.current.preview || ""
                anchors.centerIn: parent
                width: Math.min(preferredWidth, parent.width - 20)
                height: Math.min(preferredHeight, parent.height - 12)
            }
        }
        Text {
            objectName: "editorialSlideTitle"
            text: editorial.current.title || ""
            color: theme.text; font.pixelSize: 24; font.bold: true
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }
        Text {
            objectName: "editorialSlideDescription"
            text: editorial.current.description || ""
            color: theme.muted; font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true; wrapMode: Text.WordWrap
        }
        Text {
            visible: editorial.slides.length > 1
            text: (editorial.index + 1) + " of " + editorial.slides.length
            color: theme.muted; font.pixelSize: 13
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
        }
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            Row {
                id: slideNavigation
                objectName: "editorialSlideNavigation"
                anchors.centerIn: parent
                spacing: 10
                visible: editorial.slides.length > 1
                StoneButton {
                    objectName: "editorialPrevious"
                    label: "‹"; accessibilityLabel: "Previous slide"
                    size: "inline"; width: 40
                    enabled: editorial.index > 0
                    onActivated: editorial.index--
                }
                StoneButton {
                    objectName: "editorialNext"
                    label: "›"; accessibilityLabel: "Next slide"
                    size: "inline"; width: 40
                    enabled: editorial.index < editorial.slides.length - 1
                    onActivated: editorial.index++
                }
            }
            StoneButton {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: editorial.index === editorial.slides.length - 1
                label: editorial.finishLabel
                emphasized: true
                width: Math.max(110, implicitWidth)
                onActivated: editorial.finish(editorial.finishLabel === "Try it")
            }
            StoneButton {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                visible: editorial.finishLabel === "Start using VODForge" && editorial.index < editorial.slides.length - 1
                label: "Skip tour"; size: "inline"; width: 95
                onActivated: editorial.finish(false)
            }
        }
    }
    ColumnLayout {
        objectName: "welcomeSingleScreen"
        visible: editorial.showSocialInvitation
        anchors.fill: parent
        anchors.margins: 12
        spacing: 16
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 8
            Image {
                source: assetUrl + "brand/vf-mark.png"
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                fillMode: Image.PreserveAspectFit
            }
            Row {
                Text { text: "VOD"; color: theme.accent; font.pixelSize: 17; font.bold: true }
                Text { text: "Forge"; color: theme.text; font.pixelSize: 17; font.bold: true }
            }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }
        Row {
            Layout.alignment: Qt.AlignHCenter
            spacing: 10
            Repeater {
                model: ["library.png", "watch.png", "forge.png"]
                Image {
                    width: 176
                    height: 122
                    rotation: index === 0 ? -5 : index === 2 ? 5 : 0
                    source: assetUrl + "onboarding/" + modelData
                    sourceSize.width: 880
                    sourceSize.height: 592
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                }
            }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 8 }
        Text {
            objectName: "welcomeHeadline"
            text: "Your videos. Ready when you are."
            color: theme.text
            font.pixelSize: 29
            font.bold: true
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        Text {
            text: "Download, organize and watch in one place."
            color: theme.muted
            font.pixelSize: 15
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
        }
        Item { Layout.preferredHeight: 5 }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 10
            StoneButton {
                objectName: "welcomeSocialFollow"
                sceneIcon: "x"
                label: "Follow @VODForge"
                accessibilityLabel: "Follow VODForge on X"
                quiet: true
                size: "inline"
                Layout.preferredHeight: 34
                onActivated: editorial.socialFollowRequested()
            }
            Text {
                text: "Fast support · platform updates"
                color: theme.muted
                font.pixelSize: 12
            }
        }
        Item { Layout.fillHeight: true; Layout.minimumHeight: 6 }
        StoneButton {
            objectName: "welcomeGetStarted"
            label: editorial.finishLabel
            emphasized: true
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 200
            Layout.preferredHeight: 44
            onActivated: editorial.finish(false)
        }

    }

}
