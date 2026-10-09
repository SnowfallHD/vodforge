import QtQuick
import QtQuick.Controls
import QtQuick.Window

// Qt owns the native menu and standard editing selectors. Native panels need
// these selectors; QML editors use the currently focused item's public methods.
MenuBar {
    id: menuBar
    required property var appWindow
    required property var controller
    required property bool navigationAllowed
    signal outputFolderRequested()
    signal urlListRequested()
    signal settingsRequested()

    function edit(method) {
        const item = appWindow.activeFocusItem
        if (item && typeof item[method] === "function") item[method]()
    }

    Menu {
        title: qsTr("File")
        Action { text: qsTr("Load URL List…"); enabled: menuBar.navigationAllowed; shortcut: StandardKey.Open; onTriggered: menuBar.urlListRequested() }
        Action { text: qsTr("Choose Output Folder…"); enabled: menuBar.navigationAllowed; onTriggered: menuBar.outputFolderRequested() }
        MenuSeparator {}
        Action { text: qsTr("Settings…"); enabled: menuBar.navigationAllowed; shortcut: StandardKey.Preferences; onTriggered: menuBar.settingsRequested() }
        MenuSeparator {}
        Action { text: qsTr("Quit VODForge"); shortcut: StandardKey.Quit; onTriggered: appWindow.close() }
    }
    Menu {
        title: qsTr("Edit")
        Action { text: qsTr("Undo"); shortcut: StandardKey.Undo; onTriggered: menuBar.edit("undo") }
        Action { text: qsTr("Redo"); shortcut: StandardKey.Redo; onTriggered: menuBar.edit("redo") }
        MenuSeparator {}
        Action { text: qsTr("Cut"); shortcut: StandardKey.Cut; onTriggered: menuBar.edit("cut") }
        Action { text: qsTr("Copy"); shortcut: StandardKey.Copy; onTriggered: menuBar.edit("copy") }
        Action { text: qsTr("Paste"); shortcut: StandardKey.Paste; onTriggered: menuBar.edit("paste") }
        Action { text: qsTr("Select All"); shortcut: StandardKey.SelectAll; onTriggered: menuBar.edit("selectAll") }
    }
    Menu {
        title: qsTr("View")
        enabled: menuBar.navigationAllowed
        Action { text: qsTr("Forge"); enabled: menuBar.navigationAllowed; shortcut: "Ctrl+1"; onTriggered: controller.select("Forge") }
        Action { text: qsTr("Library"); enabled: menuBar.navigationAllowed; shortcut: "Ctrl+2"; onTriggered: controller.select("Library") }
        Action { text: qsTr("Watch"); enabled: menuBar.navigationAllowed; shortcut: "Ctrl+3"; onTriggered: controller.select("Watch") }
        Action { text: qsTr("Activity"); enabled: menuBar.navigationAllowed; shortcut: "Ctrl+4"; onTriggered: controller.select("Activity") }

    }
    Menu {
        title: qsTr("Window")
        Action { text: qsTr("Minimize"); shortcut: "Ctrl+M"; onTriggered: appWindow.showMinimized() }
        Action {
            text: qsTr("Zoom")
            onTriggered: appWindow.visibility === Window.Maximized ? appWindow.showNormal() : appWindow.showMaximized()
        }
        MenuSeparator {}
        Action { text: qsTr("Bring VODForge to Front"); onTriggered: { appWindow.show(); appWindow.raise(); appWindow.requestActivate() } }
    }
    Menu {
        title: qsTr("Help")
        enabled: menuBar.navigationAllowed
        Action { text: qsTr("Welcome Tour"); enabled: menuBar.navigationAllowed; onTriggered: controller.openWelcomeTour() }
        Action { text: qsTr("What’s New"); enabled: menuBar.navigationAllowed && controller.whatsNewAvailable; onTriggered: controller.openWhatsNew() }
        MenuSeparator {}
        Action { text: qsTr("Contact Support…"); enabled: menuBar.navigationAllowed; onTriggered: controller.openSupport("feedback") }
        Action { text: qsTr("Privacy Details"); enabled: menuBar.navigationAllowed; onTriggered: controller.openPrivacy() }
    }
}
