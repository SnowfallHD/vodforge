import QtQuick
import QtQuick.Controls

ToolTip {
    id: tooltip
    property real reveal: 0
    property bool singleLine: false
    readonly property var overlayItem: Overlay.overlay
    readonly property point anchorPosition: parent && overlayItem ? parent.mapToItem(overlayItem, 0, 0) : Qt.point(0, 0)
    padding: 10
    margins: 12
    x: parent ? Math.max(margins - anchorPosition.x,
            Math.min((parent.width - width) / 2,
                (overlayItem ? overlayItem.width : width + margins * 2) - margins - anchorPosition.x - width)) : 0
    y: parent ? (overlayItem && anchorPosition.y + parent.height + 6 + height > overlayItem.height - margins
            ? Math.max(margins - anchorPosition.y, -height - 6) : parent.height + 6) : 0
    width: Math.min(singleLine ? Number.MAX_VALUE : 420,
            overlayItem ? Math.max(1, overlayItem.width - margins * 2) : 420,
            tooltipLabel.implicitWidth + leftPadding + rightPadding)
    enter: Transition {
        NumberAnimation { target: tooltip; property: "reveal"; from: 0; to: 1; duration: bridge.reducedMotion ? 0 : 240; easing.type: Easing.InOutCubic }
    }
    exit: Transition {
        NumberAnimation { target: tooltip; property: "reveal"; to: 0; duration: bridge.reducedMotion ? 0 : 180; easing.type: Easing.InOutCubic }
    }
    background: LiquidSurface { reveal: tooltip.reveal }
    contentItem: Text {
        id: tooltipLabel
        objectName: "liquidTooltipLabel"
        text: tooltip.text
        color: theme.text
        font.pixelSize: 13
        wrapMode: tooltip.singleLine ? Text.NoWrap : Text.WrapAnywhere
        elide: tooltip.singleLine ? Text.ElideRight : Text.ElideNone
        opacity: Math.max(0, (tooltip.reveal - 0.65) / 0.35)
    }
}
