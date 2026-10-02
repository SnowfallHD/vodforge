import QtQuick

// A local surface extension, not a modal or an input-owning popup.
Item {
    id: notice
    property string message: ""
    property bool expanded: false
    property bool reducedMotion: false
    property bool modal: false
    property real reveal: expanded ? 1 : 0
    property real availableWidth: 440
    readonly property real targetWidth: Math.min(availableWidth, Math.max(120, metrics.advanceWidth + 36))
    width: targetWidth
    height: Math.min(116, label.implicitHeight + 32)
    visible: expanded || reveal > 0
    z: 100
    function open() { expanded = true }
    function close() { expanded = false }
    Behavior on reveal {
        NumberAnimation { duration: notice.reducedMotion ? 0 : 240; easing.type: Easing.InOutCubic }
    }
    TextMetrics { id: metrics; text: notice.message; font.pixelSize: 14 }
    Canvas {
        id: face
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections { target: notice; function onRevealChanged() { face.requestPaint() } }
        onPaint: {
            const c = getContext("2d")
            c.clearRect(0, 0, width, height)
            const p = notice.reveal
            if (p <= 0) return
            const w = width * (0.24 + 0.76 * p)
            const left = (width - w) / 2, right = left + w
            const bottom = height * p, r = Math.min(16, bottom / 2)
            // Concave shoulders smoothly join the small neck to the text face.
            c.beginPath()
            c.moveTo(left - 12 * p, 0)
            c.bezierCurveTo(left + r, 0, left, r, left, r)
            c.lineTo(left, bottom - r)
            c.quadraticCurveTo(left, bottom, left + r, bottom)
            c.lineTo(right - r, bottom)
            c.quadraticCurveTo(right, bottom, right, bottom - r)
            c.lineTo(right, r)
            c.bezierCurveTo(right, r, right - r, 0, right + 12 * p, 0)
            c.fillStyle = theme.bg
            c.fill()
            c.strokeStyle = theme.border
            c.lineWidth = 1
            c.stroke()
            // Cover the shared shell border at the joining edge.
            c.fillRect(left + 1, 0, w - 2, 2)
        }
    }
    Text {
        id: label
        x: 18; y: 13
        width: parent.width - 36
        text: notice.message
        color: theme.text
        font.pixelSize: 14
        wrapMode: Text.WordWrap
        maximumLineCount: 4
        elide: Text.ElideRight
        opacity: Math.max(0, (notice.reveal - 0.8) / 0.2)
        clip: true
        height: Math.max(0, Math.min(84, implicitHeight, notice.height * notice.reveal - 20))
        Accessible.role: Accessible.StaticText
        Accessible.name: notice.message
    }
}
