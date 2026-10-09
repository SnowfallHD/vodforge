import QtQuick

Column {
    id: selector
    property var options: []
    property string currentValue: ""
    property string buttonText: ""
    property string buttonObjectName: ""
    property bool expanded: false
    property real reveal: expanded ? 1 : 0
    Behavior on reveal {
        NumberAnimation { duration: bridge.reducedMotion ? 0 : 240; easing.type: Easing.InOutCubic }
    }
    signal chosen(string value)
    spacing: 4

    // Follow the growing choices only when they cross the nearest viewport edge.
    // Deferring lets the surrounding layouts update their content height first.
    function revealChoices() {
        if (!expanded || !visible) return
        let viewport = parent
        while (viewport && !(viewport instanceof Flickable)) viewport = viewport.parent
        if (!viewport) return
        const bottom = mapToItem(viewport.contentItem, 0, height).y
        const overflow = bottom - (viewport.contentY + viewport.height)
        if (overflow > 0) {
            const maximum = Math.max(viewport.originY,
                viewport.originY + viewport.contentHeight - viewport.height)
            viewport.contentY = Math.min(maximum, viewport.contentY + overflow)
        }
    }
    onHeightChanged: { if (expanded) Qt.callLater(revealChoices) }
    onExpandedChanged: { if (expanded) Qt.callLater(revealChoices) }

    onVisibleChanged: { if (!visible) expanded = false }

    StoneButton {
        objectName: selector.buttonObjectName
        width: parent.width
        height: 39
        label: selector.buttonText + (selector.expanded ? "  ▴" : "  ▾")
        onActivated: selector.expanded = !selector.expanded
    }
    Item {
        visible: selector.expanded || selector.reveal > 0
        width: parent.width
        height: (choices.implicitHeight + 8) * selector.reveal
        clip: true
        StoneField {
            objectName: "inlineSelectorConcaveSurface"
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width * (0.30 + 0.70 * selector.reveal)
            height: parent.height
        }
        Column {
            id: choices
            opacity: Math.max(0, (selector.reveal - 0.4) / 0.6)
            x: 4; y: 4
            width: parent.width - 8
            spacing: 2
            Repeater {
                model: selector.options
                StoneButton {
                    required property var modelData
                    objectName: selector.objectName + "_option_" + modelData.value
                    width: parent.width
                    height: 36
                    label: modelData.label
                    selected: selector.currentValue === modelData.value
                    onActivated: { selector.chosen(modelData.value); selector.expanded = false }
                }
            }
        }
    }
}
