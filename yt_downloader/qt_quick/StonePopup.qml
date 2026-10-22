import QtQuick
import QtQuick.Controls

Popup {
    id: popup
    focus: true
    property real surfaceOpacity: 0.84
    property real materialWidth: width
    property real materialHeight: height
    // Opt in only app-owned dropdowns; modal/native surfaces keep their policy.
    property bool liquidMotion: false
    property real reveal: liquidMotion ? 0 : 1
    enter: Transition {
        NumberAnimation { target: popup; property: "reveal"; to: 1; duration: popup.liquidMotion && !bridge.reducedMotion ? 240 : 0; easing.type: Easing.InOutCubic }
    }
    exit: Transition {
        NumberAnimation { target: popup; property: "reveal"; to: 0; duration: popup.liquidMotion && !bridge.reducedMotion ? 180 : 0; easing.type: Easing.InOutCubic }
    }
    Binding {
        target: popup.contentItem
        property: "opacity"
        when: popup.liquidMotion
        value: Math.max(0, (popup.reveal - 0.65) / 0.35)
    }
    property Item triggerItem
    property bool dismissedByTriggerPress: false
    property bool closingFromTrigger: false
    property bool exitInProgress: false

    function toggleFrom(trigger) {
        if (triggerItem !== trigger) dismissedByTriggerPress = false
        triggerItem = trigger
        if (visible && !exitInProgress) {
            closingFromTrigger = true
            dismissedByTriggerPress = false
            close()
            // Do not carry trigger ownership into a later, distinct gesture.
            closingFromTrigger = false
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
    onAboutToShow: exitInProgress = false
    onClosed: exitInProgress = false
    onAboutToHide: {
        exitInProgress = true
        dismissedByTriggerPress = !closingFromTrigger && !!triggerItem &&
                                  bridge.isPointerPressOnItem(triggerItem)
        closingFromTrigger = false
    }
    Connections {
        target: bridge
        function onPointerGestureEnded() { popup.dismissedByTriggerPress = false }
    }
    Connections {
        target: popup.triggerItem
        ignoreUnknownSignals: true
        function onHoveredChanged() {
            // Leaving and returning during the same held click must not turn
            // its outside-press dismissal into a new open on release.
            if (!popup.triggerItem.hovered && !bridge.isPointerPressed())
                popup.dismissedByTriggerPress = false
        }
    }
    background: StoneField {
        id: surface
        x: (popup.width - width) / 2
        y: 0
        width: popup.width * (popup.liquidMotion ? 0.30 + 0.70 * popup.reveal : 1)
        height: popup.height * (popup.liquidMotion ? popup.reveal : 1)
        opacity: popup.liquidMotion ? popup.reveal : 1
        surfaceOpacity: popup.surfaceOpacity
        materialWidth: popup.materialWidth
        materialHeight: popup.materialHeight
        Image {
            objectName: "popupElevationShadow"
            // Paint outside the face without expanding the popup's input area.
            x: -24; y: -24
            width: surface.width + 48
            height: surface.height + 48
            z: -1
            source: surface.visible ? "image://vodforge/popup-shadow/"
                    + Math.max(1, Math.round(popup.materialWidth)) + "/"
                    + Math.max(1, Math.round(popup.materialHeight)) : ""
            fillMode: Image.Stretch
            cache: true
            smooth: true
        }
    }
}
