import QtQuick
import QtQuick.Controls

Popup {
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
