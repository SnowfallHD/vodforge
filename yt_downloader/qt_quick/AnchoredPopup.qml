import QtQuick
import QtQuick.Controls
import QtQuick.Window

StonePopup {
    id: popup
    liquidMotion: true
    // Menus share one inset; a menu sizes to its rows unless it sets a height.
    padding: menuMetrics.padding
    property Item anchorItem
    property Item scrollViewport
    property bool preferAbove: false
    property bool alignRight: false
    property bool openRight: false
    property int overlap: 3
    // A right-click menu opens at the pointer: a point in anchorItem's
    // coordinates. Null for menus opened from a button.
    property var anchorPoint: null
    // Distance kept from the window edge.
    property int edgeMargin: 8

    // A value dropdown (a field showing its current choice) is at least as
    // wide as that field; action menus keep their own width.
    function fieldWidth(minimum) {
        return Math.max(minimum, anchorItem ? anchorItem.width : 0)
    }

    // Exact height of a scrolling list of `count` standard menu rows.
    function rowsHeight(count) {
        return Math.max(0, count * menuMetrics.row + (count - 1) * menuMetrics.gap)
               + topPadding + bottomPadding
    }

    // Snap to the display's pixel grid: crisp edges, and on a Retina screen
    // within a quarter point of a card that sits at a fractional position.
    function snap(value) {
        const ratio = parent && parent.Screen.devicePixelRatio > 0 ? parent.Screen.devicePixelRatio : 1
        return Math.round(value * ratio) / ratio
    }

    function reposition(beforeShow = false) {
        if ((!visible && !beforeShow) || !anchorItem || !parent) return
        let owner = anchorItem
        while (owner) {
            if (!owner.visible) {
                close()
                return
            }
            owner = owner.parent
        }
        if (scrollViewport) {
            const inView = anchorItem.mapToItem(scrollViewport, 0, 0)
            if (inView.y + anchorItem.height <= 0 || inView.y >= scrollViewport.height ||
                    inView.x + anchorItem.width <= 0 || inView.x >= scrollViewport.width) {
                close()
                return
            }
        }
        const point = anchorItem.mapToItem(parent, 0, 0)
        // Limits: inside the parent, and a margin inside the window, so a
        // popup never touches the window edge but stays flush with a parent
        // edge that lies inside the window.
        const root = parent.Window.window ? parent.Window.window.contentItem : null
        const origin = root ? parent.mapFromItem(root, 0, 0) : Qt.point(0, 0)
        const minX = Math.max(0, root ? origin.x + edgeMargin : 0)
        const maxX = Math.min(parent.width, root ? origin.x + root.width - edgeMargin : parent.width)
        const minY = Math.max(0, root ? origin.y + edgeMargin : 0)
        const maxY = Math.min(parent.height, root ? origin.y + root.height - edgeMargin : parent.height)
        if (anchorPoint) {
            // Like a native context menu: below and to the right of the
            // pointer, flipped to the other side where there is no room.
            const at = anchorItem.mapToItem(parent, anchorPoint.x, anchorPoint.y)
            const right = at.x + width <= maxX
            const down = at.y + height <= maxY
            growUp = !down
            x = snap(Math.max(minX, Math.min(maxX - width, right ? at.x : at.x - width)))
            y = snap(Math.max(minY, Math.min(maxY - height, down ? at.y : at.y - height)))
            return
        }
        const below = point.y + anchorItem.height - overlap
        const above = point.y - height + overlap
        const fitsAbove = above >= minY
        const fitsBelow = below + height <= maxY
        const useAbove = (preferAbove && fitsAbove) || (!fitsBelow && fitsAbove)
        growUp = useAbove
        const preferredX = openRight ? point.x + anchorItem.width - overlap :
                           alignRight ? point.x + anchorItem.width - width : point.x
        // A popup wider than the space left starts at the left limit.
        x = snap(Math.max(minX, Math.min(maxX - width, preferredX)))
        y = snap(Math.max(minY, Math.min(maxY - height, useAbove ? above : below)))
    }
    onAboutToShow: reposition(true)
    onOpened: reposition()
    onAnchorItemChanged: reposition()
    onWidthChanged: reposition()
    onHeightChanged: reposition()
    Connections {
        target: popup.scrollViewport ? popup.scrollViewport.contentItem : null
        function onContentXChanged() { popup.reposition() }
        function onContentYChanged() { popup.reposition() }
    }
    Connections {
        target: popup.anchorItem
        function onXChanged() { popup.reposition() }
        function onYChanged() { popup.reposition() }
        function onVisibleChanged() { popup.reposition() }
    }
    Timer {
        interval: 100
        repeat: true
        running: popup.visible
        onTriggered: popup.reposition()
    }
}
