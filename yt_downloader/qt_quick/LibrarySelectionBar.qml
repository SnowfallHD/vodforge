import QtQuick

Flow {
    property var ownerScene
    property string section: "media"
    property bool sectionVisible: true
    property string actionsObjectName: "librarySelectionActionsButton"
    visible: sectionVisible && ownerScene.selectionMode && ownerScene.selectionSection === section
    height: visible ? implicitHeight : 0
    spacing: 12
    Text {
        text: ownerScene.selectedEntityCount ? ownerScene.selectedEntityCount + " selected" : "Select items"
        color: theme.muted
        font.pixelSize: 14
        height: 40
        verticalAlignment: Text.AlignVCenter
    }
    StoneButton {
        objectName: parent.objectName + "SelectAll"
        label: "Select all"
        width: 105; height: 40
        onActivated: ownerScene.selectAllSelection()
    }
    StoneButton {
        objectName: parent.objectName + "Clear"
        label: "Clear"
        width: 75; height: 40
        enabled: ownerScene.selectedEntityCount > 0
        onActivated: ownerScene.clearSelection()
    }
    StoneButton {
        objectName: actionsObjectName
        visible: ownerScene.selectedEntityCount > 0
        label: "Actions…"
        width: 175; height: 40
        onActivated: ownerScene.openSelectionActions(section, this)
    }
}
