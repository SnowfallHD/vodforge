import QtQuick

Canvas {
    id: surface
    property real reveal: 1.0
    property color fillColor: theme.bg
    property color borderColor: theme.border
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onRevealChanged: requestPaint()
    onPaint: {
        const c = getContext("2d")
        c.clearRect(0, 0, width, height)
        const p = surface.reveal
        if (p <= 0) return
        const w = (width - 2) * (0.30 + 0.70 * p)
        const left = (width - w) / 2, right = left + w
        const top = 1, bottom = Math.max(top, (height - 1) * p)
        const r = Math.min(8, (bottom - top) / 2)
        c.beginPath()
        c.moveTo(left + r, top)
        c.lineTo(right - r, top)
        c.quadraticCurveTo(right, top, right, top + r)
        c.lineTo(right, bottom - r)
        c.quadraticCurveTo(right, bottom, right - r, bottom)
        c.lineTo(left + r, bottom)
        c.quadraticCurveTo(left, bottom, left, bottom - r)
        c.lineTo(left, top + r)
        c.quadraticCurveTo(left, top, left + r, top)
        c.closePath()
        c.fillStyle = surface.fillColor
        c.fill()
        c.strokeStyle = surface.borderColor
        c.lineWidth = 1
        c.stroke()
    }
}
