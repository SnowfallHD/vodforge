import QtQuick

Column {
    id: selector
    property var options: []
    property string currentValue: ""
    property string buttonText: ""
    property string buttonObjectName: ""
    property bool expanded: false
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
    StoneField {
        visible: selector.expanded
        width: parent.width
        height: choices.implicitHeight + 8
        Column {
            id: choices
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
                    onActivated: selector.chosen(modelData.value)
                }
            }
        }
    }
}
