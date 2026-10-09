import QtQuick
import QtQuick.Controls

ToolTip {
    id: tooltip
    property real reveal: 0
    padding: 10
    margins: 12
    x: parent ? (parent.width - width) / 2 : 0
    y: parent ? parent.height + 6 : 0
    width: Math.min(420, implicitWidth)
    enter: Transition {
        NumberAnimation { target: tooltip; property: "reveal"; from: 0; to: 1; duration: bridge.reducedMotion ? 0 : 240; easing.type: Easing.InOutCubic }
    }
    exit: Transition {
        NumberAnimation { target: tooltip; property: "reveal"; to: 0; duration: bridge.reducedMotion ? 0 : 180; easing.type: Easing.InOutCubic }
    }
    background: LiquidSurface { reveal: tooltip.reveal }
    contentItem: Text {
        text: tooltip.text
        color: theme.text
        font.pixelSize: 13
        wrapMode: Text.WrapAnywhere
        opacity: Math.max(0, (tooltip.reveal - 0.65) / 0.35)
    }
}
