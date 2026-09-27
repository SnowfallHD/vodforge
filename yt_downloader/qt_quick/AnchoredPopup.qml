import QtQuick
import QtQuick.Controls

Popup {
    id: popup
    property Item anchorItem
    property Item scrollViewport
    property bool preferAbove: false
    property bool alignRight: false
    property bool openRight: false
    property int overlap: 3

    function reposition() {
        if (!visible || !anchorItem || !parent) return
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
        const below = point.y + anchorItem.height - overlap
        const above = point.y - height + overlap
        const fitsAbove = above >= 0
        const fitsBelow = below + height <= parent.height
        const useAbove = (preferAbove && fitsAbove) || (!fitsBelow && fitsAbove)
        x = Math.max(0, Math.min(parent.width - width,
                                 openRight ? point.x + anchorItem.width - overlap :
                                 alignRight ? point.x + anchorItem.width - width : point.x))
        y = Math.max(0, Math.min(parent.height - height, useAbove ? above : below))
    }
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
