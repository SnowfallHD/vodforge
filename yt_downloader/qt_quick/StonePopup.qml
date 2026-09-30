import QtQuick
import QtQuick.Controls

Popup {
    id: popup
    focus: true
    property Item triggerItem
    property bool dismissedByTriggerPress: false
    property bool closingFromTrigger: false

    function toggleFrom(trigger) {
        if (triggerItem !== trigger) dismissedByTriggerPress = false
        triggerItem = trigger
        if (visible) {
            closingFromTrigger = true
            dismissedByTriggerPress = false
            close()
            return false
        }
        // Qt dismisses on pointer press outside before the trigger's click.
        // Consume that same click instead of treating it as a new open request.
        if (dismissedByTriggerPress) {
            dismissedByTriggerPress = false
            return false
        }
        open()
        return true
    }
    onAboutToHide: {
        dismissedByTriggerPress = !closingFromTrigger && !!triggerItem &&
                                  !!triggerItem.hovered && bridge.isPointerPressed()
        closingFromTrigger = false
    }
    Connections {
        target: popup.triggerItem
        ignoreUnknownSignals: true
        function onHoveredChanged() {
            if (!popup.triggerItem.hovered) popup.dismissedByTriggerPress = false
        }
    }
    background: StoneField {
        id: surface
        Image {
            objectName: "popupElevationShadow"
            // Paint outside the face without expanding the popup's input area.
            x: -24; y: -24
            width: surface.width + 48
            height: surface.height + 48
            z: -1
            source: surface.visible ? "image://vodforge/popup-shadow/"
                    + Math.max(1, Math.round(surface.width)) + "/"
                    + Math.max(1, Math.round(surface.height)) : ""
            fillMode: Image.Stretch
            cache: true
            smooth: true
        }
    }
}
