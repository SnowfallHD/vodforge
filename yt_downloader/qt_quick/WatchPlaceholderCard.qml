import QtQuick

Item {
    id: placeholder
    objectName: "watchPlaceholderCard"
    property string sectionTitle: ""
    width: 280
    height: 100

    StoneField { anchors.fill: parent }
    SceneIcon {
        name: placeholder.sectionTitle === "Channels" ? "channels" :
              placeholder.sectionTitle === "Playlists" ? "list" : "videos"
        tone: theme.border
        x: placeholder.sectionTitle === "Recently Added" ? (parent.width - 44) / 2 : 30
        y: placeholder.sectionTitle === "Recently Added" ? 35 : 28
        width: 44; height: 44
    }
    Rectangle {
        x: placeholder.sectionTitle === "Recently Added" ? 26 : 110
        y: placeholder.sectionTitle === "Recently Added" ? 92 : 39
        width: Math.max(20, parent.width - (placeholder.sectionTitle === "Recently Added" ? 96 : 196))
        height: 10; radius: 5; color: theme.border
    }
    Rectangle {
        x: placeholder.sectionTitle === "Recently Added" ? 26 : 110
        y: placeholder.sectionTitle === "Recently Added" ? 111 : 61
        width: Math.max(20, parent.width / 2 - 54)
        height: 10; radius: 5; color: theme.border
    }
}
