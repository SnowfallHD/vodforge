import QtQuick
import QtQuick.Controls

ToolTip {
    id: tooltip
    // A native header has no body-sized overlay for an item tooltip. Qt's
    // tooltip window keeps this informative surface outside its input aperture.
    property bool independentWindow: false
    popupType: independentWindow ? Popup.Window : Popup.Item
    property real reveal: 0
    property bool singleLine: false
    readonly property var overlayItem: independentWindow ? null : Overlay.overlay
    // Optional pointer x in the parent's coordinates. When set, the tip opens
    // centered on the pointer instead of the middle of a wide parent.
    property real pointerX: NaN
    // Measured each time the tip opens. A binding to mapToItem() is evaluated
    // once, before layouts place the parent, and then never again because
    // nothing it reads changes: the tip opened hundreds of pixels away.
    property point anchorPosition: Qt.point(0, 0)
    property real openedPointerX: NaN
    function measureAnchor() {
        anchorPosition = parent && overlayItem ? parent.mapToItem(overlayItem, 0, 0) : Qt.point(0, 0)
        openedPointerX = pointerX
    }
    onAboutToShow: measureAnchor()
    readonly property real centerX: parent ? (isNaN(openedPointerX) ? parent.width / 2 : openedPointerX) : 0
    padding: 10
    margins: 12
    x: parent ? Math.max(margins - anchorPosition.x,
            Math.min(centerX - width / 2,
                (overlayItem ? overlayItem.width : width + margins * 2) - margins - anchorPosition.x - width)) : 0
    y: parent ? (overlayItem && anchorPosition.y + parent.height + 6 + height > overlayItem.height - margins
            ? Math.max(margins - anchorPosition.y, -height - 6) : parent.height + 6) : 0
    width: Math.min(singleLine ? Number.MAX_VALUE : 420,
            overlayItem ? Math.max(1, overlayItem.width - margins * 2) : 420,
            tooltipLabel.implicitWidth + leftPadding + rightPadding)
    enter: Transition {
        NumberAnimation { target: tooltip; property: "reveal"; from: 0; to: 1; duration: motion.tipIn; easing.type: Easing.OutCubic }
    }
    exit: Transition {
        NumberAnimation { target: tooltip; property: "reveal"; to: 0; duration: motion.tipOut; easing.type: Easing.OutCubic }
    }
    background: LiquidSurface { reveal: tooltip.reveal; growUp: tooltip.y < 0 }
    contentItem: Text {
        id: tooltipLabel
        objectName: "liquidTooltipLabel"
        text: tooltip.text
        color: theme.text
        font.pixelSize: 13
        wrapMode: tooltip.singleLine ? Text.NoWrap : Text.WrapAnywhere
        elide: tooltip.singleLine ? Text.ElideRight : Text.ElideNone
        opacity: Math.max(0, (tooltip.reveal - 0.6) / 0.4)
    }
}
