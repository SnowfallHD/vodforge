import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: scene
    property var appBridge
    readonly property var projection: appBridge.watchScene
    readonly property string route: projection.route || "home"
    readonly property var videos: projection.videos || []

    RowLayout {
        id: browseHeader
        width: parent.width
        height: 46
        spacing: 8
        StoneButton {
            label: "Playlists"
            size: "inline"
            Layout.preferredWidth: 118
            onActivated: scene.appBridge.navigateWatch("playlists")
        }
        StoneButton {
            label: "Categories"
            size: "inline"
            Layout.preferredWidth: 126
            onActivated: scene.appBridge.navigateWatch("collections")
        }
        StoneButton {
            label: "Channels"
            size: "inline"
            Layout.preferredWidth: 112
            onActivated: scene.appBridge.navigateWatch("channels")
        }
        Item { Layout.fillWidth: true }
        TextField {
            id: searchField
            objectName: "watchSavedSearch"
            Accessible.name: "Search saved videos"
            Layout.preferredWidth: Math.min(240, Math.max(160, scene.width - 460))
            Layout.preferredHeight: 40
            placeholderText: "Search saved videos"
            placeholderTextColor: theme.muted
            color: theme.text
            font.pixelSize: 15
            background: StoneField {}
            onTextEdited: scene.appBridge.setWatchSearch(text)
        }
    }
    Connections {
        target: scene.appBridge
        function onHistoryChanged() {
            if (searchField.text !== scene.projection.query)
                searchField.text = scene.projection.query
        }
    }

    ScrollView {
        id: viewport
        y: browseHeader.height + 12
        width: parent.width
        height: parent.height - y
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Column {
            width: viewport.availableWidth
            spacing: 13

            StoneButton {
                visible: scene.route !== "home"
                label: scene.projection.backLabel || "Back to Watch"
                width: 160
                height: 40
                onActivated: scene.appBridge.backWatch()
            }
            RowLayout {
                visible: scene.route !== "home"
                width: parent.width
                height: 49
                Text {
                    text: scene.projection.query ? "Search results" : scene.route === "group" ? scene.projection.groupTitle :
                          scene.route.charAt(0).toUpperCase() + scene.route.slice(1)
                    color: theme.text
                    font.pixelSize: 34
                    font.bold: true
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
            Row {
                visible: scene.route === "group" && scene.videos.length > 0
                width: parent.width
                height: visible ? 44 : 0
                spacing: 12
                StoneButton {
                    label: "Play " + (scene.projection.queueKind === "channel" ? "channel" : "playlist")
                    width: 150
                    height: 40
                    onActivated: scene.appBridge.startWatchQueue(scene.projection.queueKeys, scene.projection.queueKind, false)
                }
                StoneButton {
                    label: "Shuffle"
                    width: 120
                    height: 40
                    enabled: scene.videos.length > 1
                    onActivated: scene.appBridge.startWatchQueue(scene.projection.queueKeys, scene.projection.queueKind, true)
                }
            }
            Item {
                visible: scene.route === "home" && !!scene.projection.hero.owner
                width: parent.width
                height: visible ? 250 : 0
                Text { x: 18; y: 12; text: "READY TO WATCH"; color: theme.muted; font.pixelSize: 12; font.bold: true }
                Text { x: 18; y: 45; width: parent.width - 36; text: scene.projection.hero.title || ""; color: theme.text; font.pixelSize: 38; font.bold: true; elide: Text.ElideRight }
                Row {
                    x: 18; y: 104; spacing: 12
                    Text { text: scene.projection.hero.creator || ""; color: theme.text; font.pixelSize: 14 }
                    Text { text: scene.projection.hero.type || ""; color: theme.muted; font.pixelSize: 14 }
                }
                Row {
                    x: 18; y: 182; spacing: 13
                    StoneButton { label: "Play"; icon: "image://vodforge/icon/play.png"; width: 136; height: 42; onActivated: scene.appBridge.openLibraryOwner(scene.projection.hero.owner) }
                    StoneButton { label: "View in Library"; icon: "image://vodforge/icon/folder-20.png"; width: 178; height: 42; onActivated: { scene.appBridge.select("Library"); scene.appBridge.navigateLibrary("all") } }
                }
            }

            Row {
                width: parent.width
                spacing: 18
            Repeater {
                model: [
                    { route: "playlists", title: "Playlists", items: scene.projection.playlists || [] },
                    { route: "channels", title: "Channels", items: scene.projection.channels || [] },
                    { route: "collections", title: "Collections", items: scene.projection.collections || [] }
                ]
                Column {
                    required property var modelData
                    visible: (scene.route === "home" && modelData.route !== "collections") || scene.route === modelData.route
                    width: scene.route === "home" ? (parent.width - 18) / 2 : parent.width
                    spacing: 9
                    RowLayout {
                        width: parent.width
                        height: 39
                        Text { text: modelData.title; color: theme.text; font.pixelSize: 23; font.bold: true; Layout.fillWidth: true }
                        StoneButton {
                            visible: scene.route === "home"
                            label: "See All"
                            size: "inline"
                            Layout.preferredWidth: 86
                            onActivated: scene.appBridge.navigateWatch(modelData.route)
                        }
                    }
                    Flow {
                        width: parent.width
                        spacing: 12
                        Repeater {
                            model: scene.route === "home" ? modelData.items.slice(0, 1) : modelData.items
                            StoneButton {
                                required property var modelData
                                width: scene.route === "home" ? parent.width : Math.max(164, (parent.width - 36) / 4)
                                height: scene.route === "home" ? 136 : 158
                                label: ""
                                accessibilityLabel: modelData.title + ", " + modelData.count + " saved item(s)"
                                onActivated: scene.appBridge.navigateWatchGroup(modelData.kind, modelData.key)
                                Image {
                                    x: 4; y: 4; width: parent.width - 8; height: 101
                                    source: modelData.artwork
                                    visible: source.toString().length > 0
                                    fillMode: Image.PreserveAspectCrop
                                    smooth: true
                                }
                                Text { x: 12; y: 111; width: parent.width - 24; text: modelData.title; color: theme.text; font.pixelSize: 15; font.bold: true; elide: Text.ElideRight }
                                Text { x: 12; y: 133; text: modelData.count + " saved"; color: theme.muted; font.pixelSize: 12 }
                            }
                        }
                    }
                }
            }
            }

            Column {
                visible: scene.route === "home" && (scene.projection.collections || []).length > 0
                width: parent.width
                spacing: 9
                RowLayout {
                    width: parent.width
                    height: 39
                    Text { text: "Collections"; color: theme.text; font.pixelSize: 23; font.bold: true; Layout.fillWidth: true }
                    StoneButton { label: "See All"; size: "inline"; Layout.preferredWidth: 86; onActivated: scene.appBridge.navigateWatch("collections") }
                }
                Flow {
                    width: parent.width
                    spacing: 12
                    Repeater {
                        model: (scene.projection.collections || []).slice(0, 4)
                        StoneButton {
                            required property var modelData
                            width: Math.max(164, (parent.width - 36) / 4)
                            height: 145
                            label: ""
                            accessibilityLabel: modelData.title + ", " + modelData.count + " saved item(s)"
                            onActivated: scene.appBridge.navigateWatchGroup(modelData.kind, modelData.key)
                            Image { x: 4; y: 4; width: parent.width - 8; height: 96; source: modelData.artwork; visible: source.toString().length > 0; fillMode: Image.PreserveAspectCrop; smooth: true }
                            Text { x: 11; y: 106; width: parent.width - 22; text: modelData.title; color: theme.text; font.pixelSize: 15; font.bold: true; elide: Text.ElideRight }
                            Text { x: 11; y: 128; text: modelData.count + " saved"; color: theme.muted; font.pixelSize: 12 }
                        }
                    }
                }
            }

            RowLayout {
                visible: scene.route === "home" || scene.route === "videos" || scene.route === "group"
                width: parent.width
                height: 42
                Text { text: scene.route === "home" ? "Recently Added" : scene.route === "group" ? "Saved media" : "Videos"; color: theme.text; font.pixelSize: 23; font.bold: true; Layout.fillWidth: true }
                StoneButton {
                    visible: scene.route === "home"
                    label: "See All"
                    size: "inline"
                    Layout.preferredWidth: 86
                    onActivated: scene.appBridge.navigateWatch("videos")
                }
            }
            Flow {
                id: mediaFlow
                visible: scene.route === "home" || scene.route === "videos" || scene.route === "group"
                width: parent.width
                spacing: 12
                Repeater {
                    model: scene.videos
                    StoneButton {
                        required property var modelData
                        width: Math.max(164, (mediaFlow.width - 36) / 4)
                        height: 178
                        label: ""
                        accessibilityLabel: "Play " + modelData.title
                        onActivated: scene.appBridge.openLibraryOwner(modelData.owner)
                        Image {
                            x: 4; y: 4; width: parent.width - 8; height: 105
                            source: modelData.artwork
                            visible: source.toString().length > 0
                            fillMode: Image.PreserveAspectCrop
                            smooth: true
                        }
                        Text { x: 11; y: 115; width: parent.width - 22; text: modelData.title; color: theme.text; font.pixelSize: 14; font.bold: true; elide: Text.ElideRight }
                        Text { x: 11; y: 139; width: parent.width - 22; text: modelData.creator; color: theme.muted; font.pixelSize: 12; elide: Text.ElideRight }
                    }
                }
            }
            Text {
                visible: scene.videos.length === 0 &&
                         (scene.route === "home" || scene.route === "videos" || scene.route === "group")
                text: "No saved media yet"
                color: theme.muted
                font.pixelSize: 16
            }
            Item { width: 1; height: 18 }
        }
    }
}
