import QtQuick

WheelHandler {
    id: handler
    property var nestedScrollView
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad

    // Trackpad phases delimit gestures. Phase-less mouse wheels use 180 ms
    // of idle as a practical new-gesture boundary (not a native phase claim).
    property bool gestureActive: false
    property bool mayChain: false
    property int gestureDirection: 0
    property Timer idleTimer: Timer {
        id: mouseIdle
        objectName: "verticalScrollGestureIdle"
        interval: 180
        onTriggered: handler.gestureActive = false
    }

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
        if (wheel.phase === Qt.ScrollBegin) gestureActive = false
        if (wheel.phase === Qt.NoScrollPhase) mouseIdle.restart()
        else mouseIdle.stop()
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
        const direction = dy > 0 ? 1 : -1
        if (!gestureActive) {
            const minimum = inner.originY || 0
            const maximum = minimum + Math.max(0, inner.contentHeight - inner.height)
            mayChain = direction > 0 ? inner.contentY <= minimum : inner.contentY >= maximum
            gestureDirection = direction
            gestureActive = true
        }
        let remaining = consume(inner, dy)
        // Reaching an edge during a gesture never transfers its remainder or
        // momentum to the page. Reversal still scrolls the inner view normally.
        if (!mayChain || direction !== gestureDirection) remaining = 0
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
