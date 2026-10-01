import QtQuick

WheelHandler {
    id: handler
    property var nestedScrollView
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad

    // Return only the unconsumed part; an edge-crossing event must not be
    // replayed in full on the page or swallowed by the inner ScrollView.
    function consume(view, delta) {
        const minimum = view.originY || 0
        const maximum = minimum + Math.max(0, view.contentHeight - view.height)
        const before = Math.max(minimum, Math.min(maximum, view.contentY))
        const after = Math.max(minimum, Math.min(maximum, before - delta))
        view.contentY = after
        return delta + after - before
    }

    onWheel: function(wheel) {
        const dx = wheel.pixelDelta.x || wheel.angleDelta.x / 120 * 80
        const dy = wheel.pixelDelta.y || wheel.angleDelta.y / 120 * 80
        // Match the rails' tolerance for sideways trackpad drift. Horizontal
        // gestures remain available to the existing horizontal handlers.
        if (!nestedScrollView || !nestedScrollView.contentItem || dy === 0 ||
                Math.abs(dy) < Math.abs(dx) * 0.2) {
            wheel.accepted = false
            return
        }
        const inner = nestedScrollView.contentItem
        let remaining = consume(inner, dy)
        let ancestor = inner.parent
        while (ancestor && remaining !== 0) {
            if (typeof ancestor.contentY === "number" &&
                    typeof ancestor.contentHeight === "number" &&
                    typeof ancestor.originY === "number") {
                remaining = consume(ancestor, remaining)
            }
            ancestor = ancestor.parent
        }
        // We own this vertical event, even at the outermost edge. Allowing
        // default handling now would apply the original delta a second time.
        wheel.accepted = true
    }
}
