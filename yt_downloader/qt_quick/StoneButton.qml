import QtQuick

Item {
    id: control
    property string label: ""
    property string accessibilityLabel: label
    property string icon: ""
    property string sceneIcon: ""
    property bool selected: false
    property bool emphasized: false
    property bool transientMaterial: true
    property bool hoverMaterial: true
    property bool interactive: true
    property bool quiet: false
    property string size: "default"
    readonly property bool overflowGlyph: !icon.length && !sceneIcon.length &&
            ["⋯", "⋮", "…"].indexOf(label) >= 0
    readonly property bool hovered: mouse.containsMouse
    readonly property bool activeFace: (hoverMaterial && hovered) || activeFocus || selected
    // Artwork cards keep their content inside the same inset face in every state.
    readonly property int artworkFaceInset: 7 + (activeFace && transientMaterial ? 2 : 0)
    signal activated()
    signal doubleActivated()
    implicitWidth: Math.max(2 * buttonMetrics[size].horizontalPadding + caption.implicitWidth
                            + ((icon.length || sceneIcon.length) ? buttonMetrics[size].iconPixels + (label.length ? 8 : 0) : 0), 44)
    implicitHeight: buttonMetrics[size].height
    opacity: control.enabled ? 1 : 0.5
    activeFocusOnTab: control.interactive && control.enabled
    Accessible.role: control.interactive ? Accessible.Button : Accessible.StaticText
    Accessible.name: control.accessibilityLabel
    Accessible.ignored: !control.interactive && control.accessibilityLabel.length === 0
    Accessible.focusable: control.interactive && control.enabled
    Accessible.focused: control.activeFocus
    Accessible.selected: control.selected
    Accessible.onPressAction: {
        if (control.interactive && control.enabled) control.activated()
    }

    Image {
        property string presentationRole: "control"
        anchors.fill: parent
        visible: !control.quiet || mouse.pressed || mouse.containsMouse || control.activeFocus
        source: "image://vodforge/button/" + Math.max(1, Math.round(control.width))
                + "/" + Math.max(1, Math.round(control.height)) + "/"
                + (!control.transientMaterial || !control.enabled ? "normal" : mouse.pressed ? "pressed" : (control.activeFace ? "hover" : "normal"))
                + "/" + (control.emphasized ? "1" : "0") + "/r" + bridge.themeRevision
        fillMode: Image.Stretch
        cache: true
        smooth: true
    }
    Row {
        anchors.centerIn: control.quiet ? undefined : parent
        anchors.left: control.quiet ? parent.left : undefined
        anchors.leftMargin: control.quiet ? 8 : 0
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8
        Image {
            objectName: "stoneButtonIcon"
            property string presentationRole: "control"
            visible: control.icon.length > 0
            width: visible ? buttonMetrics[control.size].iconPixels : 0
            height: buttonMetrics[control.size].iconPixels
            source: control.icon
            fillMode: Image.PreserveAspectFit
            smooth: true
        }
        SceneIcon {
            property string presentationRole: "control"
            visible: control.sceneIcon.length > 0
            width: visible ? buttonMetrics[control.size].iconPixels : 0
            height: width
            name: control.sceneIcon
            tone: control.emphasized ? theme.action : theme.icon
        }
        Text {
            id: caption
            objectName: "stoneButtonCaption"
            visible: control.label.length > 0 && !control.overflowGlyph
            text: control.label
            readonly property real availableWidth: Math.max(0, control.width
                    - ((control.icon.length || control.sceneIcon.length) ? buttonMetrics[control.size].iconPixels + (control.label.length ? 8 : 0) : 0))
            readonly property real sidePadding: Math.min(
                    buttonMetrics[control.size].horizontalPadding,
                    Math.max(8, (availableWidth - implicitWidth) / 2))
            width: Math.min(implicitWidth, Math.max(0, availableWidth - 2 * sidePadding))
            elide: Text.ElideRight
            color: control.emphasized ? theme.action :
                   control.quiet && !control.selected && !control.hovered && !control.activeFocus ? theme.muted : theme.text
            font.family: buttonFontFamily
            font.pixelSize: buttonMetrics[control.size].fontPixels
            font.weight: control.quiet && control.selected ? Font.DemiBold : Font.Normal
            anchors.verticalCenter: parent.verticalCenter
        }
    }
    // Overflow punctuation has font-dependent bearings and baseline placement.
    // Draw the shared symbol around the face centre, independent of text metrics.
    Item {
        id: overflowDots
        objectName: "stoneButtonOverflowGlyph"
        visible: control.overflowGlyph
        anchors.fill: parent
        readonly property real span: buttonMetrics[control.size].fontPixels
        readonly property real diameter: Math.max(2, span * 0.15)
        readonly property bool vertical: control.label === "⋮"
        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: overflowDots.diameter
                height: width
                radius: width / 2
                antialiasing: true
                x: overflowDots.width / 2 - width / 2 +
                   (overflowDots.vertical ? 0 : (index - 1) * overflowDots.span * 0.26)
                y: overflowDots.height / 2 - height / 2 +
                   (overflowDots.vertical ? (index - 1) * overflowDots.span * 0.26 : 0)
                color: caption.color
            }
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: control.interactive && control.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: control.activated()
        onDoubleClicked: control.doubleActivated()
    }
    Keys.onReturnPressed: { if (control.interactive && control.enabled) control.activated() }
    Keys.onSpacePressed: { if (control.interactive && control.enabled) control.activated() }
}
