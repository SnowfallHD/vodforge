import QtQuick

WheelHandler {
    property var nestedScrollView
    target: null
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad

    function hasVerticalOverflow(view) {
        return view.contentHeight > view.height
    }

    function consume(view, delta) {
        const minimum = view.originY || 0
        const maximum = minimum + Math.max(0, view.contentHeight - view.height)
        const before = Math.max(minimum, Math.min(maximum, view.contentY))
        view.contentY = Math.max(minimum, Math.min(maximum, before - delta))
    }

    onWheel: function(wheel) {
        const dx = wheel.pixelDelta.x || wheel.angleDelta.x / 120 * 80
        const dy = wheel.pixelDelta.y || wheel.angleDelta.y / 120 * 80
        // Horizontal input remains available to the existing horizontal handlers.
        if (!nestedScrollView || !nestedScrollView.contentItem || dy === 0 ||
                Math.abs(dy) < Math.abs(dx) * 0.2) {
            wheel.accepted = false
            return
        }
        const inner = nestedScrollView.contentItem
        if (hasVerticalOverflow(inner)) {
            // An overflowing field owns vertical input under its pointer,
            // including at either edge. Move outside the field to scroll the page.
            consume(inner, dy)
        } else {
            // Content may shrink while input is in flight. Clear an obsolete
            // offset and route immediately to the nearest scrollable ancestor.
            consume(inner, 0)
            let ancestor = inner.parent
            while (ancestor) {
                if (typeof ancestor.contentY === "number" &&
                        typeof ancestor.contentHeight === "number" &&
                        typeof ancestor.originY === "number" &&
                        hasVerticalOverflow(ancestor)) {
                    consume(ancestor, dy)
                    break
                }
                ancestor = ancestor.parent
            }
        }
        // Prevent default handling from replaying the original delta.
        wheel.accepted = true
    }
}
