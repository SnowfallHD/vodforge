import QtQuick

WheelHandler {
    id: handler
    property var horizontalView
    property var verticalView
    signal scrolled(bool horizontal)
    target: null
    // The default accepts mouse wheels only. macOS sends trackpad gestures
    // as TouchPad events, so the rail must own those gestures explicitly.
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: function(wheel) {
        if (!horizontalView || !verticalView ||
                !horizontalView.contentItem || !verticalView.contentItem) {
            wheel.accepted = false
            return
        }
        // Trackpads report fine pixel deltas, including momentum after a fast swipe.
        // Mouse wheels usually report only angle deltas.
        const dx = wheel.pixelDelta.x || wheel.angleDelta.x / 120 * 80
        const dy = wheel.pixelDelta.y || wheel.angleDelta.y / 120 * 80
        // During a vertical trackpad swipe, sideways drift can briefly exceed
        // the vertical delta. Keep that motion on the page, including momentum.
        if (dy !== 0 && Math.abs(dy) >= Math.abs(dx) * 0.2) {
            const page = verticalView.contentItem
            const previous = page.contentY
            page.contentY = Math.max(0, Math.min(page.contentHeight - verticalView.height,
                                                page.contentY - dy))
            if (page.contentY !== previous) handler.scrolled(false)
        } else if (dx !== 0) {
            const rail = horizontalView.contentItem
            const previous = rail.contentX
            rail.contentX = Math.max(0, Math.min(rail.contentWidth - horizontalView.width,
                                                rail.contentX - dx))
            if (rail.contentX !== previous) handler.scrolled(true)
        } else {
            wheel.accepted = false
            return
        }
        wheel.accepted = true
    }
}
