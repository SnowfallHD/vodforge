import QtQuick

// Floating feedback does not participate in the composer or page layout.
Item {
    id: notice
    property string message: ""
    property bool expanded: false
    property bool reducedMotion: false
    property bool modal: false
    property bool attached: false
    property real reveal: expanded ? 1 : 0
    property real availableWidth: 440
    readonly property real targetWidth: Math.min(availableWidth, Math.max(120, metrics.advanceWidth + 36))
    width: targetWidth
    height: Math.min(116, label.implicitHeight + 20)
    visible: expanded || reveal > 0
    z: 100
    function open() { expanded = true }
    function close() { expanded = false }
    Behavior on reveal {
        NumberAnimation { duration: notice.reducedMotion ? 0 : 240; easing.type: Easing.InOutCubic }
    }
    TextMetrics { id: metrics; text: notice.message; font.pixelSize: 14 }
    LiquidSurface { anchors.fill: parent; reveal: notice.reveal; visible: !notice.attached }
    Text {
        id: label
        x: 18; y: 9
        width: parent.width - 36
        text: notice.message
        color: theme.text
        font.pixelSize: 14
        wrapMode: Text.WordWrap
        maximumLineCount: 4
        elide: Text.ElideRight
        opacity: Math.max(0, (notice.reveal - 0.65) / 0.35)
        clip: true
        height: Math.min(84, implicitHeight)
        Accessible.role: Accessible.StaticText
        Accessible.name: notice.message
    }
}
