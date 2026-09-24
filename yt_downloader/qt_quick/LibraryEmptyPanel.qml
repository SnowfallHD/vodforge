import QtQuick

Item {
    id: panel
    property bool collections: false
    property bool filtered: false
    property bool actions: true
    signal forgeRequested()
    signal importRequested()
    signal clearRequested()
    height: actions ? 232 : 188

    StoneField { anchors.fill: parent }
    Rectangle {
        x: (parent.width - 70) / 2
        y: 20
        width: 70; height: 70; radius: 35
        color: theme.panel
        SceneIcon {
            anchors.centerIn: parent
            name: panel.collections ? "folder" : "download"
            tone: theme.muted
            width: 28; height: 28
        }
    }
    Text {
        x: 0; y: 103; width: parent.width
        text: panel.filtered ? "No matching media" : panel.collections ? "No collections yet" : "No downloads yet"
        color: theme.text
        font.pixelSize: 21
        font.bold: true
        horizontalAlignment: Text.AlignHCenter
    }
    Text {
        x: 20; y: 137; width: parent.width - 40
        text: panel.filtered ? "Try a different search or clear your filters." :
            panel.collections ? "Your collections will appear here once you start downloading content from Forge." :
            "Downloads from Forge will appear here automatically."
        color: theme.muted
        font.pixelSize: 14
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }
    StoneButton {
        objectName: "libraryEmptyClearFilters"
        visible: panel.filtered
        x: (parent.width - 168) / 2; y: 173
        width: 168; height: 44
        label: "Clear filters"
        onActivated: panel.clearRequested()
    }
    Row {
        visible: panel.actions && !panel.filtered
        x: (parent.width - 376) / 2; y: 173
        spacing: 16
        StoneButton {
            objectName: "libraryEmptyGoForge"
            width: 177; height: 44
            label: "Go to Forge"
            emphasized: true
            onActivated: panel.forgeRequested()
        }
        StoneButton {
            objectName: "libraryEmptyImportMedia"
            width: 183; height: 44
            label: "Import Media"
            onActivated: panel.importRequested()
        }
    }
}
