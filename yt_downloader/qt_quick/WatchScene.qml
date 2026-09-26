import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: scene
    property var appBridge
    readonly property var projection: appBridge.watchScene
    readonly property string route: projection.route || "home"
    readonly property var videos: projection.videos || []
    readonly property bool emptyHome: route === "home" && videos.length === 0
    readonly property string viewKey: route + "|" + (projection.query || "") + "|" +
        (projection.groupKind || "") + "|" + (projection.groupTitle || "")
    property string previousViewKey: ""
    property var scrollPositions: ({})
    property bool restoreOnNextRoute: false
    property string moreOwner: ""
    Component.onCompleted: previousViewKey = viewKey
    function back() {
        restoreOnNextRoute = true
        appBridge.backWatch()
    }
    onViewKeyChanged: {
        if (!viewport || !viewport.contentItem) return
        if (previousViewKey)
            scrollPositions[previousViewKey] = viewport.contentItem.contentY
        const destination = restoreOnNextRoute ? (scrollPositions[viewKey] || 0) : 0
        const targetKey = viewKey
        previousViewKey = viewKey
        restoreOnNextRoute = false
        Qt.callLater(function() {
            if (scene.viewKey === targetKey && viewport.contentItem)
                viewport.contentItem.contentY = destination
        })
    }
    function showLibraryDetails(owner) {
        scene.appBridge.openWatchDetails(owner)
    }
    function openMore(owner) {
        moreOwner = owner
        morePopup.open()
    }

    Popup {
        id: morePopup
        x: Math.max(0, scene.width - width - 16)
        y: Math.min(scene.height - height, 290)
        width: 270
        height: 104
        padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 3
            StoneButton {
                width: parent.width; height: 46
                label: "View in Library"
                onActivated: { morePopup.close(); scene.showLibraryDetails(scene.moreOwner) }
            }
            StoneButton {
                width: parent.width; height: 46
                label: "Browse personal categories"
                onActivated: { morePopup.close(); scene.appBridge.navigateWatch("collections") }
            }
        }
    }

    RowLayout {
        id: browseHeader
        visible: scene.route !== "home"
        width: parent.width
        height: visible ? 46 : 0
        spacing: 8
        StoneButton {
            objectName: "watchBackButton"
            label: "← Back"
            size: "inline"
            Layout.preferredWidth: 104
            onActivated: scene.back()
        }
    }

    ScrollView {
        id: viewport
        objectName: "watchViewport"
        y: browseHeader.visible ? browseHeader.height + 12 : 0
        width: parent.width
        height: parent.height - y
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Column {
            width: viewport.availableWidth
            spacing: 13

            RowLayout {
                visible: scene.route !== "home" && scene.route !== "group"
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
            WatchEmptyScene {
                visible: scene.emptyHome
                width: parent.width
                appBridge: scene.appBridge
            }
            Item {
                id: groupHeader
                visible: scene.route === "group" && scene.videos.length > 0
                width: parent.width
                readonly property bool channel: scene.projection.groupKind === "channel"
                readonly property int textLeft: channel ? width >= 1000 ? 214 : width >= 680 ? 174 : 32 : 0
                height: groupActions.y + groupActions.childrenRect.height + 16
                clip: true
                Image {
                    anchors.fill: parent
                    visible: groupHeader.channel && source.toString().length > 0
                    source: scene.projection.groupBanner || ""
                    fillMode: Image.PreserveAspectCrop
                    smooth: true
                    opacity: 0.24
                }
                ArtworkImage {
                    objectName: "watchGroupAvatarImage"
                    x: 32
                    y: 42
                    width: groupHeader.width >= 1000 ? 150 : 112
                    height: width
                    source: scene.projection.groupAvatar || ""
                    circular: true
                    visible: groupHeader.channel && hasArtwork
                }
                Text {
                    id: groupTitle
                    x: groupHeader.textLeft
                    y: groupHeader.channel ? 38 : 6
                    width: parent.width - x - 32
                    text: scene.projection.groupTitle || ""
                    color: theme.text
                    font.pixelSize: groupHeader.channel ? 32 : 40
                    font.bold: true
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Text {
                    id: groupDescription
                    objectName: "watchGroupDescription"
                    x: groupHeader.textLeft
                    y: groupTitle.y + groupTitle.implicitHeight + 14
                    width: Math.min(760, parent.width - x - 32)
                    text: groupHeader.channel ? (scene.projection.groupDescription || "Your saved media and playlists from " + scene.projection.groupTitle + ".") :
                          scene.projection.groupSubtitle
                    color: theme.muted
                    font.pixelSize: 16
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
                Text {
                    id: groupCount
                    objectName: "watchGroupCountLabel"
                    visible: groupHeader.channel
                    x: groupHeader.textLeft
                    y: groupDescription.y + groupDescription.implicitHeight + 18
                    text: scene.projection.groupCountLabel
                    color: theme.muted
                    font.pixelSize: 15
                }
                Flow {
                    id: groupActions
                    x: groupHeader.textLeft
                    y: groupHeader.channel ? groupCount.y + groupCount.implicitHeight + 20 : groupDescription.y + groupDescription.implicitHeight + 26
                    width: parent.width - x - 16
                    spacing: 14
                    StoneButton {
                        visible: groupHeader.channel || scene.videos.length > 1
                        label: groupHeader.channel ? "Play Channel" : "Play playlist"
                        emphasized: true
                        width: groupHeader.channel ? 155 : 154
                        height: 40
                        onActivated: scene.appBridge.startWatchQueue(scene.projection.queueKeys, scene.projection.queueKind, false)
                    }
                    StoneButton {
                        visible: scene.videos.length > 1
                        label: "Shuffle"
                        width: 125
                        height: 40
                        onActivated: scene.appBridge.startWatchQueue(scene.projection.queueKeys, scene.projection.queueKind, true)
                    }
                    StoneButton {
                        visible: groupHeader.channel
                        label: "View in Library"
                        width: 180
                        height: 40
                        onActivated: scene.showLibraryDetails(scene.projection.groupFirstOwner)
                    }
                }
            }
            Item {
                visible: scene.route === "home" && !scene.emptyHome && !!scene.projection.hero.owner
                width: parent.width
                height: visible ? Math.max(350, heroActions.y + heroActions.height + 36) : 0
                clip: true
                Image {
                    anchors.fill: parent
                    source: scene.projection.hero.backdrop || ""
                    visible: source.toString().length > 0
                    fillMode: Image.PreserveAspectCrop
                    smooth: true
                    opacity: 0.2
                }
                Text {
                    x: 36; y: 44
                    text: scene.projection.hero.resume ?
                          (scene.projection.hero.kind === "audio" ? "CONTINUE LISTENING" : "CONTINUE WATCHING") :
                          (scene.projection.hero.kind === "video" ? "READY TO WATCH" : "READY TO PLAY")
                    color: theme.muted; font.pixelSize: 12; font.bold: true
                }
                Text {
                    id: heroTitle
                    x: 36; y: 72
                    width: Math.min(parent.width - 72, Math.max(268, Math.min(620, parent.width * 0.55)))
                    text: scene.projection.hero.title || ""
                    color: theme.text; font.pixelSize: parent.width >= 1000 ? 40 : 32; font.bold: true
                    wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                }
                Row {
                    id: heroChips
                    x: 36; y: heroTitle.y + heroTitle.implicitHeight + 14; spacing: 12
                    Text { text: scene.projection.hero.creator || ""; color: theme.text; font.pixelSize: 14 }
                    Text { text: scene.projection.hero.playlist || ""; color: theme.muted; font.pixelSize: 14 }
                    Text { text: scene.projection.hero.type || ""; color: theme.muted; font.pixelSize: 14 }
                    Text { text: scene.projection.hero.duration || ""; color: theme.muted; font.pixelSize: 14 }
                }
                Text {
                    id: heroDescription
                    x: 36; y: heroChips.y + 46
                    width: heroTitle.width
                    text: scene.projection.hero.description || "Your saved media, ready to watch."
                    color: theme.muted; font.pixelSize: 16
                    wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
                }
                Rectangle {
                    id: heroProgressTrack
                    visible: !!scene.projection.hero.resume
                    x: 40; y: Math.max(242, heroDescription.y + heroDescription.implicitHeight + 28)
                    width: Math.min(400, heroTitle.width - 130)
                    height: 8; radius: 4; color: theme.border
                    Rectangle { width: parent.width * (scene.projection.hero.progress || 0); height: parent.height; radius: 4; color: theme.progress }
                }
                Text {
                    visible: heroProgressTrack.visible
                    x: heroProgressTrack.x + heroProgressTrack.width + 16
                    y: heroProgressTrack.y - 8
                    text: scene.projection.hero.progressLabel || ""
                    color: theme.text; font.pixelSize: 15
                }
                Row {
                    id: heroActions
                    x: 36
                    y: scene.projection.hero.resume ? heroProgressTrack.y + 30 : Math.max(272, heroDescription.y + heroDescription.implicitHeight + 32)
                    spacing: 16
                    height: 42
                    StoneButton { label: scene.projection.hero.resume ? "Resume" : "Play"; icon: "image://vodforge/icon/play.png/r" + scene.appBridge.themeRevision; width: 150; height: 42; onActivated: scene.appBridge.playWatchHero(scene.projection.hero.owner) }
                    StoneButton { label: "View in Library"; icon: "image://vodforge/icon/folder-20.png/r" + scene.appBridge.themeRevision; width: 181; height: 42; onActivated: scene.showLibraryDetails(scene.projection.hero.owner) }
                    StoneButton { label: "⋯"; accessibilityLabel: "More actions"; width: 54; height: 42; onActivated: scene.openMore(scene.projection.hero.owner) }
                }
            }

            Column {
                width: parent.width
                spacing: 18
            Repeater {
                objectName: "watchGroupRoutesRepeater"
                model: [
                    { route: "playlists", title: "Playlists", items: scene.projection.playlists || [] },
                    { route: "channels", title: "Channels", items: scene.projection.channels || [] },
                    { route: "collections", title: "Collections", items: scene.projection.collections || [] }
                ]
                Column {
                    required property var modelData
                    visible: (scene.route === "home" && !scene.emptyHome && modelData.route !== "collections") || scene.route === modelData.route
                    width: parent.width
                    spacing: 9
                    RowLayout {
                        visible: scene.route === "home"
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
                    ScrollView {
                        id: homeRail
                        objectName: "watchHomeRail_" + modelData.route
                        visible: scene.route === "home" && modelData.route !== "collections"
                        width: parent.width
                        height: visible ? (modelData.route === "channels" ? 101 : 180) : 0
                        clip: true
                        ScrollBar.vertical.policy: ScrollBar.AlwaysOff
                        ScrollBar.horizontal.policy: ScrollBar.AsNeeded
                        property int loadedCount: 6
                        onVisibleChanged: { if (visible) loadedCount = 6 }
                        Connections {
                            target: homeRail.contentItem
                            function onContentXChanged() {
                                if (!homeRail.visible || !homeRail.contentItem ||
                                        homeRail.contentItem.contentX <= 0) return
                                if (homeRail.contentItem.contentX + homeRail.width >=
                                        homeRail.contentItem.contentWidth - 500)
                                    homeRail.loadedCount = Math.min(modelData.items.length,
                                                                    homeRail.loadedCount + 6)
                            }
                        }
                Row {
                    spacing: 12
                    WheelHandler {
                        target: null
                        onWheel: function(wheel) {
                            if (Math.abs(wheel.angleDelta.y) > Math.abs(wheel.angleDelta.x)) {
                                viewport.contentItem.contentY = Math.max(0,
                                    Math.min(viewport.contentItem.contentHeight - viewport.height,
                                             viewport.contentItem.contentY - wheel.angleDelta.y))
                                wheel.accepted = true
                            } else wheel.accepted = false
                        }
                    }
                            Repeater {
                                objectName: "watchHomeGroupRepeater"
                                model: homeRail.visible ? modelData.items.slice(0, homeRail.loadedCount) : []
                                WatchGroupCard {
                                    required property var modelData
                                    width: modelData.kind === "channel" ? 260 : 225
                                    group: modelData
                                    appBridge: scene.appBridge
                                    projection: scene.projection
                                    onChosen: scene.appBridge.navigateWatchGroup(modelData.kind, modelData.key)
                                }
                            }
                        }
                    }
                    Flow {
                        id: groupFlow
                        objectName: "watchGroupFlow"
                        visible: scene.route !== "home"
                        width: parent.width
                        spacing: 12
                        readonly property var items: scene.route === modelData.route ? modelData.items : []
                        readonly property real cardWidth: Math.max(164, (width - 36) / 4)
                        readonly property real cardHeight: modelData.route === "channels" ? 82 : 161
                        readonly property int columns: Math.max(1, Math.floor((width + spacing) / (cardWidth + spacing)))
                        readonly property real rowStride: cardHeight + spacing
                        readonly property int totalRows: Math.ceil(items.length / columns)
                        readonly property real scrollTop: viewport.contentItem.contentY -
                            (groupFlow.y + groupFlow.parent.y + groupFlow.parent.parent.y)
                        readonly property int firstRow: Math.max(0, Math.min(totalRows, Math.floor(scrollTop / rowStride) - 1))
                        readonly property int lastRow: Math.min(totalRows, firstRow + Math.ceil(viewport.height / rowStride) + 3)
                        Item {
                            visible: groupFlow.firstRow > 0
                            width: groupFlow.width
                            height: Math.max(0, groupFlow.firstRow * groupFlow.rowStride - groupFlow.spacing)
                        }
                        Repeater {
                            objectName: "watchGroupRepeater"
                            model: groupFlow.items.slice(groupFlow.firstRow * groupFlow.columns,
                                                         groupFlow.lastRow * groupFlow.columns)
                            WatchGroupCard {
                                required property var modelData
                                width: groupFlow.cardWidth
                                group: modelData
                                appBridge: scene.appBridge
                                projection: scene.projection
                                onChosen: scene.appBridge.navigateWatchGroup(modelData.kind, modelData.key)
                            }
                        }
                        Item {
                            visible: groupFlow.lastRow < groupFlow.totalRows
                            width: groupFlow.width
                            height: Math.max(0, (groupFlow.totalRows - groupFlow.lastRow) * groupFlow.rowStride - groupFlow.spacing)
                        }
                    }
                }
            }
            }

            Column {
                visible: scene.route === "home" && !scene.emptyHome && (scene.projection.collections || []).length > 0
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
                        WatchGroupCard {
                            required property var modelData
                            width: Math.max(164, (parent.width - 36) / 4)
                            group: modelData
                            appBridge: scene.appBridge
                            projection: scene.projection
                            onChosen: scene.appBridge.navigateWatchGroup(modelData.kind, modelData.key)
                        }
                    }
                }
            }

            RowLayout {
                visible: (scene.route === "home" && !scene.emptyHome) || scene.route === "group"
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
                objectName: "watchMediaFlow"
                visible: (scene.route === "home" && !scene.emptyHome) || scene.route === "videos" || scene.route === "group"
                width: parent.width
                height: Math.max(0, totalRows * rowStride - spacing)
                spacing: 12
                readonly property int columns: Math.max(1, Math.min(4, Math.floor((width + spacing) / 200)))
                readonly property real cardWidth: Math.max(164, (width - spacing * (columns - 1)) / columns)
                readonly property real rowStride: 174
                readonly property int displayCount: scene.route === "home" ? Math.min(scene.videos.length, columns) : scene.videos.length
                readonly property int totalRows: Math.ceil(displayCount / columns)
                readonly property real scrollTop: viewport.contentItem.contentY - y
                readonly property int firstRow: scene.route === "home" ? 0 :
                    Math.max(0, Math.min(totalRows, Math.floor(scrollTop / rowStride) - 1))
                readonly property int lastRow: scene.route === "home" ? totalRows :
                    Math.min(totalRows, firstRow + Math.ceil(viewport.height / rowStride) + 3)
                Item {
                    visible: mediaFlow.firstRow > 0
                    width: mediaFlow.width
                    height: Math.max(0, mediaFlow.firstRow * mediaFlow.rowStride - mediaFlow.spacing)
                }
                Repeater {
                    objectName: "watchMediaRepeater"
                    model: scene.videos.slice(mediaFlow.firstRow * mediaFlow.columns,
                                              Math.min(mediaFlow.displayCount, mediaFlow.lastRow * mediaFlow.columns))
                    StoneButton {
                        required property var modelData
                        width: mediaFlow.cardWidth
                        height: 162
                        label: ""
                        accessibilityLabel: "Play " + modelData.title
                        onActivated: scene.appBridge.openLibraryOwner(modelData.owner)
                        ArtworkImage {
                            objectName: "watchMediaArtworkImage"
                            x: 0; y: 0; width: parent.width; height: 113
                            cover: true
                            inset: 0
                            source: scene.projection ? scene.appBridge.mediaArtwork(modelData.owner) : ""
                        }
                        Text { x: 11; y: 115; width: parent.width - 22; text: modelData.title; color: theme.text; font.pixelSize: 14; font.bold: true; elide: Text.ElideRight }
                        Text { x: 11; y: 139; width: parent.width - 22; text: modelData.creator; color: theme.muted; font.pixelSize: 12; elide: Text.ElideRight }
                    }
                }
                Item {
                    visible: mediaFlow.lastRow < mediaFlow.totalRows
                    width: mediaFlow.width
                    height: Math.max(0, (mediaFlow.totalRows - mediaFlow.lastRow) * mediaFlow.rowStride - mediaFlow.spacing)
                }
            }
            Text {
                visible: scene.videos.length === 0 &&
                         (scene.route === "videos" || scene.route === "group")
                text: "No saved media yet"
                color: theme.muted
                font.pixelSize: 16
            }
            Item { width: 1; height: 18 }
        }
    }
}
