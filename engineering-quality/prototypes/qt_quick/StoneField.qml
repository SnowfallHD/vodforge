import QtQuick

Item {
    id: field
    property bool focused: false
    implicitHeight: 48
    Image {
        anchors.fill: parent
        source: "image://vodforge/field/" + Math.max(1, Math.round(field.width))
                + "/" + Math.max(1, Math.round(field.height))
                + "/" + (field.focused ? "focus" : "normal")
        fillMode: Image.Stretch
        cache: true
        smooth: true
    }
}
