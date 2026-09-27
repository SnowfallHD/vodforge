import QtQuick

WheelHandler {
    id: handler
    property var horizontalView
    property var verticalView
    target: null
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
        if (Math.abs(dx) > Math.abs(dy)) {
            const rail = horizontalView.contentItem
            rail.contentX = Math.max(0, Math.min(rail.contentWidth - horizontalView.width,
                                                rail.contentX - dx))
        } else if (dy !== 0) {
            const page = verticalView.contentItem
            page.contentY = Math.max(0, Math.min(page.contentHeight - verticalView.height,
                                                page.contentY - dy))
        } else {
            wheel.accepted = false
            return
        }
        wheel.accepted = true
    }
}
