import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    spacing: 8
    padding: 0
    implicitWidth: caption.implicitWidth
    implicitHeight: Math.max(28, caption.implicitHeight)
    background: null
    indicator: SceneIcon {
        x: 0
        y: (control.height - height) / 2
        width: 20; height: 20
        name: control.checked ? "checkbox-checked" : "checkbox"
        tone: !control.enabled ? theme.muted : control.activeFocus ? theme.action : theme.icon
    }
    contentItem: Text {
        id: caption
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? theme.text : theme.muted
        font.family: buttonFontFamily
        font.pixelSize: 15
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.WordWrap
    }
}
