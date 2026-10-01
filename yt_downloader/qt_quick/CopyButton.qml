import QtQuick
import QtQuick.Controls

StoneButton {
    id: control
    property var appBridge
    property string owner: ""
    property string field: ""
    property string section: ""
    property string factLabel: ""
    property string displayedText: ""
    property string tooltipText: accessibilityLabel
    property bool copied: false
    onOwnerChanged: copied = false
    onDisplayedTextChanged: copied = false
    label: "⧉"
    size: "inline"
    width: 36
    height: 28
    emphasized: copied
    Accessible.description: copied ? "Copied to clipboard" : tooltipText
    ToolTip.visible: hovered
    ToolTip.text: copied ? "Copied" : tooltipText
    onActivated: {
        if (!appBridge || !owner) return
        copied = factLabel.length ? appBridge.copyLibraryFact(owner, section, factLabel) :
            field === "note" ? appBridge.copyLibraryText(owner, field, displayedText) :
            appBridge.copyLibraryText(owner, field)
        if (copied) feedback.restart()
    }
    Timer { id: feedback; interval: 1500; onTriggered: control.copied = false }
}
