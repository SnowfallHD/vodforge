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
