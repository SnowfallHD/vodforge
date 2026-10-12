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
    // WheelHandler's default vertical orientation never emits a pure X event.
    // Keep the existing vertical owner for mixed/drifting gestures and attach
    // one horizontal-only companion to the same viewport, without a second
    // content item or replaying mixed deltas through both handlers.
    property WheelHandler horizontalHandler: WheelHandler {
        parent: handler.parent
        target: null
        orientation: Qt.Horizontal
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        onWheel: function(wheel) {
            if (wheel.pixelDelta.y !== 0 || wheel.angleDelta.y !== 0) {
                wheel.accepted = false
                return
            }
            handler.routeWheel(wheel)
        }
    }
    onWheel: function(wheel) {
        if (wheel.pixelDelta.y === 0 && wheel.angleDelta.y === 0) {
            wheel.accepted = false
            return
        }
        routeWheel(wheel)
    }
    function routeWheel(wheel) {
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
