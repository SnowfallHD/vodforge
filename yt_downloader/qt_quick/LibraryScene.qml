import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: scene
    objectName: "libraryBrowseScene"
    property var appBridge
    signal annotationRequested(int index)
    signal annotationOwnerRequested(string owner)
    signal actionsRequested(string owner)
    signal collectionRequested()
    signal categoryRequested()
    signal importRequested()
    signal selectionActionRequested(string action, var owners)

    property bool selectionMode: false
    property var selectedOwners: []
    property string groupMenuKind: ""
    property string groupMenuKey: ""
    property real groupMenuX: 0
    property real groupMenuY: 0
    function currentMenuGroup() {
        return scene.groups.find(function(group) {
            return group.kind === groupMenuKind && group.key === groupMenuKey
        })
    }
    function toggleSelection(owner) {
        if (!owner || !scene.media.some(function(item) { return item.owner === owner })) return
        var next = selectedOwners.slice()
        var index = next.indexOf(owner)
        if (index >= 0) next.splice(index, 1)
        else next.push(owner)
        selectedOwners = next
    }
    function finishSelection() { selectedOwners = []; selectionMode = false }
    function resetViewport() {
        if (viewport && viewport.contentItem) viewport.contentItem.contentY = 0
    }

    readonly property var projection: appBridge.libraryScene
    readonly property string route: projection.route || "home"
    readonly property var counts: projection.counts || ({})
    readonly property var groups: projection.groups || []
    readonly property var media: projection.media || []
    property string previousRoute: "home"
    property real browseScrollY: 0
    onRouteChanged: {
        const returningFromDetail = previousRoute === "detail"
        if (route === "detail" && viewport && viewport.contentItem)
            browseScrollY = viewport.contentItem.contentY
        finishSelection()
        if (route !== "detail" && !returningFromDetail) resetViewport()
        if (returningFromDetail) Qt.callLater(function() {
            if (viewport && viewport.contentItem && route !== "detail")
                viewport.contentItem.contentY = browseScrollY
        })
        previousRoute = route
    }
    Connections {
        target: scene.appBridge
        function onLibrarySearchChanged() { scene.resetViewport() }
        function onLibrarySortChanged() { scene.resetViewport() }
        function onLibraryCategoryChanged() { scene.resetViewport() }
    }

    LibraryDetail {
        anchors.fill: parent
        visible: scene.route === "detail"
        appBridge: scene.appBridge
        onActionsRequested: function(owner) { scene.actionsRequested(owner) }
        onAnnotationRequested: function(owner) { scene.annotationOwnerRequested(owner) }
    }

    LibraryFolders {
        anchors.fill: parent
        visible: scene.route === "folders"
        appBridge: scene.appBridge
    }

    RowLayout {
        anchors.fill: parent
        visible: scene.route !== "detail" && scene.route !== "folders"
        spacing: 0

        ColumnLayout {
            objectName: "librarySidebar"
            Layout.preferredWidth: 226
            Layout.fillHeight: true
            spacing: 4
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 50
                Text {
                    x: 14
                    y: 23
                    text: "ARCHIVE"
                    color: theme.muted
                    font.pixelSize: 11
                    font.bold: true
                }
            }
            Repeater {
                model: [
                    { route: "all", label: "All Media", icon: "folder", count: scene.counts.all || 0 },
                    { route: "channels", label: "Channels", icon: "channels", count: scene.counts.channels || 0 },
                    { route: "playlists", label: "Playlists", icon: "list", count: scene.counts.playlists || 0 },
                    { route: "videos", label: "Videos", icon: "videos", count: scene.counts.videos || 0 },
                    { route: "audio", label: "Audio", icon: "audio", count: scene.counts.audio || 0 }
                ]
                StoneButton {
                    id: categoryButton
                    required property var modelData
                    objectName: "librarySidebarButton_" + modelData.route
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    Layout.leftMargin: 8
                    Layout.rightMargin: 15
                    label: ""
                    accessibilityLabel: modelData.label + ", " + modelData.count
                    selected: scene.route === modelData.route ||
                              (scene.route === "home" && modelData.route === "all")
                    onActivated: scene.appBridge.navigateLibrary(modelData.route)
                    SceneIcon {
                        objectName: "librarySidebarIcon_" + categoryButton.modelData.route
                        name: categoryButton.modelData.icon
                        tone: categoryButton.selected ? theme.selection : theme.icon
                        x: 14
                        y: 12
                    }
                    Text {
                        x: 53
                        y: 12
                        width: parent.width - 107
                        text: categoryButton.modelData.label
                        color: theme.text
                        font.pixelSize: 15
                        elide: Text.ElideRight
                    }
                    StoneButton {
                        x: parent.width - 47
                        y: 7
                        width: 36
                        height: 31
                        label: String(categoryButton.modelData.count)
                        size: "inline"
                        interactive: false
                        transientMaterial: false
                        emphasized: categoryButton.selected
                    }
                }
            }
            StoneButton {
                label: "Folders"
                Layout.fillWidth: true
                Layout.preferredHeight: 45
                Layout.leftMargin: 8
                Layout.rightMargin: 15
                onActivated: scene.appBridge.navigateLibrary("folders")
            }
            Item { Layout.fillHeight: true }
            StoneField {
                Layout.fillWidth: true
                Layout.preferredHeight: 124
                Layout.leftMargin: 9
                Layout.rightMargin: 16
                Layout.bottomMargin: 17
                interactive: true
                accessibilityLabel: "Storage for " + scene.appBridge.storageSummary.label
                onActivated: storagePopup.open()
                Text {
                    x: 15; y: 16
                    width: parent.width - 30
                    text: scene.appBridge.storageSummary.label
                    color: theme.text
                    font.pixelSize: 13
                    font.bold: true
                    elide: Text.ElideRight
                }
                Rectangle {
                    x: 15; y: 55
                    width: parent.width - 30
                    height: 8
                    radius: 4
                    color: theme.border
                    Rectangle {
                        width: parent.width * scene.appBridge.storageSummary.fraction
                        height: parent.height
                        radius: parent.radius
                        color: theme.accent
                    }
                }
                Text {
                    x: 15; y: 76
                    width: parent.width - 30
                    text: scene.appBridge.storageSummary.detail
                    color: theme.muted
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
                Text {
                    x: 15; y: 99
                    width: parent.width - 30
                    text: scene.appBridge.storageSummary.free || ""
                    color: theme.muted
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }
        }

        Rectangle {
            objectName: "librarySidebarDivider"
            Layout.fillHeight: true
            Layout.preferredWidth: 1
            color: theme.border
        }

        ScrollView {
            id: viewport
            objectName: "libraryViewport"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 20
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                id: content
                width: viewport.availableWidth
                spacing: 13
                Text {
                    text: "Library"
                    color: theme.text
                    font.pixelSize: 37
                    font.bold: true
                }
                Text {
                    text: "Your downloaded videos, audio, and collections."
                    color: theme.muted
                    font.pixelSize: 15
                    width: parent.width
                    wrapMode: Text.WordWrap
                }
                Item { width: 1; height: 12 }

                Flow {
                    id: categoryFlow
                    objectName: "libraryCategoryFlow"
                    width: parent.width
                    spacing: 14
                    readonly property int columns: Math.max(1, Math.min(4, Math.floor((width + spacing) / 200)))
                    readonly property real cardWidth: (width - spacing * (columns - 1)) / columns
                    Repeater {
                        model: [
                            { route: "channels", label: "Channels", summary: "channel", subtitle: "Downloaded channel archives", empty: "No channel archives yet", count: scene.counts.channels || 0 },
                            { route: "playlists", label: "Playlists", summary: "playlist", subtitle: "Your curated collections", empty: "No playlists yet", count: scene.counts.playlists || 0 },
                            { route: "videos", label: "Videos", summary: "video", subtitle: "All downloaded videos", empty: "No downloaded videos", count: scene.counts.videos || 0 },
                            { route: "audio", label: "Audio", summary: "audio file", subtitle: "Music, podcasts & more", empty: "No audio files yet", count: scene.counts.audio || 0 }
                        ]
                        StoneButton {
                            id: categoryTile
                            required property var modelData
                            objectName: "libraryCategoryTile_" + modelData.route
                            width: categoryFlow.cardWidth
                            height: 106
                            label: ""
                            accessibilityLabel: modelData.label + ", " + modelData.count
                            onActivated: scene.appBridge.navigateLibrary(modelData.route)
                            readonly property bool compact: width < 220
                            readonly property int iconSize: width >= 255 ? 64 : 48
                            Rectangle {
                                visible: !categoryTile.compact
                                x: 16; y: 21
                                width: categoryTile.iconSize; height: 64
                                radius: 9
                                color: theme.accent_dark
                                SceneIcon {
                                    name: categoryTile.modelData.route === "playlists" ? "list" : categoryTile.modelData.route
                                    tone: theme.icon
                                    width: 34; height: 34
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    y: 16
                                }
                            }
                            Text {
                                x: categoryTile.compact ? 16 : categoryTile.iconSize + 36
                                y: categoryTile.compact ? 18 : 24
                                width: categoryTile.compact ? parent.width - 32 : parent.width - categoryTile.iconSize - 51
                                text: categoryTile.modelData.label
                                color: theme.text
                                font.pixelSize: categoryTile.compact ? 15 : 16
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            Text {
                                x: categoryTile.compact ? 16 : categoryTile.iconSize + 36
                                y: categoryTile.compact ? 48 : 51
                                width: categoryTile.compact ? parent.width - 32 : parent.width - categoryTile.iconSize - 51
                                text: categoryTile.compact ? String(categoryTile.modelData.count) :
                                    categoryTile.modelData.count + " " + categoryTile.modelData.summary +
                                    (categoryTile.modelData.count === 1 ? "" : "s")
                                color: theme.muted
                                font.pixelSize: categoryTile.compact ? 22 : 13
                                font.bold: categoryTile.compact
                                elide: Text.ElideRight
                            }
                            Text {
                                visible: !categoryTile.compact
                                x: categoryTile.iconSize + 36; y: 73
                                width: parent.width - categoryTile.iconSize - 51
                                text: categoryTile.modelData.count ? categoryTile.modelData.subtitle : categoryTile.modelData.empty
                                color: theme.muted
                                font.pixelSize: 10
                                elide: Text.ElideRight
                            }
                            SceneIcon {
                                visible: !categoryTile.compact
                                name: "chevron"
                                tone: theme.muted
                                x: parent.width - 29; y: 43
                                width: 17; height: 17
                            }
                        }
                    }
                }
                Item { width: 1; height: 8 }

                Row {
                    visible: scene.route === "home"
                    width: parent.width
                    height: visible ? 38 : 0
                    Text { text: "Collections"; color: theme.text; font.pixelSize: 23; font.bold: true }
                    Item { width: Math.max(0, parent.width - 200); height: 1 }
                    StoneButton {
                        label: "See All"
                        size: "inline"
                        width: 80
                        onActivated: scene.appBridge.navigateLibrary("collections")
                    }
                }
                Text {
                    visible: scene.route === "home"
                    text: "Your playlists and personal collections."
                    color: theme.muted
                    font.pixelSize: 14
                }
                Flow {
                    id: groupFlow
                    objectName: "libraryGroupFlow"
                    visible: (scene.route === "home" && scene.media.length > 0) || scene.route === "channels" ||
                             scene.route === "playlists" || scene.route === "collections"
                    width: parent.width
                    spacing: 14
                    readonly property int columns: Math.max(1, Math.min(5, Math.floor((width + spacing) / 200)))
                    readonly property real cardWidth: (width - spacing * (columns - 1)) / columns
                    readonly property var items: scene.route === "home" ? scene.groups.slice(0, columns) : scene.groups
                    readonly property real rowStride: 192 + spacing
                    readonly property int totalRows: Math.ceil(items.length / columns)
                    readonly property real scrollTop: viewport.contentItem.contentY - groupFlow.y
                    readonly property int firstRow: scene.route === "home" ? 0 :
                        Math.max(0, Math.min(totalRows, Math.floor(scrollTop / rowStride) - 1))
                    readonly property int lastRow: scene.route === "home" ? totalRows :
                        Math.min(totalRows, firstRow + Math.ceil(viewport.height / rowStride) + 3)
                    Item {
                        visible: groupFlow.firstRow > 0
                        width: groupFlow.width
                        height: Math.max(0, groupFlow.firstRow * groupFlow.rowStride - groupFlow.spacing)
                    }
                    Repeater {
                        objectName: "libraryGroupRepeater"
                        model: groupFlow.items.slice(groupFlow.firstRow * groupFlow.columns,
                                                     groupFlow.lastRow * groupFlow.columns)
                        StoneButton {
                            id: groupCard
                            required property var modelData
                            width: groupFlow.cardWidth
                            height: 192
                            label: ""
                            accessibilityLabel: modelData.title + ", " + modelData.count + " item(s)"
                            onActivated: {
                                if (scene.selectionMode) {
                                    for (const owner of modelData.owners) {
                                        if (scene.selectedOwners.indexOf(owner) < 0)
                                            scene.selectedOwners = scene.selectedOwners.concat([owner])
                                    }
                                } else scene.appBridge.navigateLibraryGroup(modelData.kind, modelData.key)
                            }
                            Image {
                                x: groupCard.modelData.kind === "channel" ? (parent.width - 96) / 2 : 0
                                y: groupCard.modelData.kind === "channel" ? 14 : 0
                                width: groupCard.modelData.kind === "channel" ? 96 : parent.width
                                height: groupCard.modelData.kind === "channel" ? 96 : 125
                                source: scene.appBridge.libraryGroupArtwork(modelData.owner, modelData.kind)
                                fillMode: Image.PreserveAspectCrop
                                visible: source.toString().length > 0
                                smooth: true
                            }
                            Text {
                                x: 14; y: 136
                                width: parent.width - 52
                                text: groupCard.modelData.title
                                color: theme.text
                                font.pixelSize: 14
                                font.bold: true
                                elide: Text.ElideRight
                            }
                            Text {
                                x: 14; y: 164
                                width: parent.width - 28
                                text: groupCard.modelData.summary
                                color: theme.muted
                                font.pixelSize: 11
                                elide: Text.ElideRight
                            }
                            StoneButton {
                                objectName: "libraryGroupMore"
                                x: parent.width - 42
                                y: 129
                                width: 36
                                height: 36
                                label: "⋮"
                                size: "inline"
                                accessibilityLabel: "More actions for " + groupCard.modelData.title
                                onActivated: {
                                    scene.groupMenuKind = groupCard.modelData.kind
                                    scene.groupMenuKey = groupCard.modelData.key
                                    const point = groupCard.mapToItem(scene, groupCard.width - 20, 129)
                                    scene.groupMenuX = Math.max(0, Math.min(scene.width - 200, point.x))
                                    scene.groupMenuY = Math.max(0, Math.min(scene.height - 100, point.y))
                                    groupMenu.open()
                                }
                            }
                        }
                    }
                    StoneButton {
                        visible: scene.route === "home"
                        objectName: "addLibraryCollectionCard"
                        width: groupFlow.cardWidth
                        height: 192
                        label: ""
                        accessibilityLabel: "Add Collection"
                        onActivated: scene.collectionRequested()
                        Rectangle {
                            x: (parent.width - 52) / 2
                            y: 30
                            width: 52; height: 52; radius: 26
                            color: theme.accent_surface
                            SceneIcon { anchors.centerIn: parent; name: "plus"; tone: theme.icon }
                        }
                        Text {
                            x: 0; y: 100; width: parent.width
                            text: "Add Collection"
                            horizontalAlignment: Text.AlignHCenter
                            color: theme.action
                            font.pixelSize: 17
                        }
                        Text {
                            x: 0; y: 130; width: parent.width
                            text: "Group downloads\nfrom any source."
                            horizontalAlignment: Text.AlignHCenter
                            color: theme.muted
                            font.pixelSize: 13
                            lineHeight: 1.5
                        }
                    }
                }
                LibraryEmptyPanel {
                    objectName: "libraryCollectionsEmptyPanel"
                    visible: (scene.route === "home" && scene.media.length === 0) ||
                        (["channels", "playlists", "collections"].indexOf(scene.route) >= 0 && scene.groups.length === 0)
                    width: parent.width
                    collections: true
                    filtered: scene.appBridge.librarySearch.length > 0
                    onForgeRequested: scene.appBridge.select("Forge")
                    onImportRequested: scene.importRequested()
                    onClearRequested: {
                        scene.appBridge.setLibrarySearch("")
                        scene.appBridge.setLibraryCategory("All categories")
                        scene.appBridge.navigateLibrary("all")
                    }
                }

                RowLayout {
                    width: parent.width
                    height: 44
                    Text {
                        text: scene.route === "home" ? "Recent Downloads" :
                              scene.route === "group" ? scene.projection.groupTitle :
                              scene.route === "all" ? "All Media" :
                              scene.route.charAt(0).toUpperCase() + scene.route.slice(1)
                        color: theme.text
                        font.pixelSize: 23
                        font.bold: true
                        Layout.fillWidth: true
                    }
                    StoneButton {
                        visible: scene.route !== "home"
                        label: "Back"
                        size: "inline"
                        Layout.preferredWidth: 72
                        onActivated: scene.appBridge.navigateLibrary("home")
                    }
                }
                Flow {
                    width: parent.width
                    height: childrenRect.height
                    spacing: 12
                    StoneField {
                        width: Math.min(200, Math.max(130, parent.width * 0.28))
                        height: 40
                        focused: localSearch.activeFocus
                        TextField {
                            id: localSearch
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            text: scene.appBridge.librarySearch
                            placeholderText: "Search media…"
                            color: theme.text
                            placeholderTextColor: theme.muted
                            background: Item {}
                            onTextEdited: scene.appBridge.setLibrarySearch(text)
                        }
                    }
                    StoneButton {
                        label: scene.appBridge.librarySort === "recent" ? "Newest first" : "Title A–Z"
                        width: 172
                        height: 40
                        onActivated: sortPopup.open()
                    }
                    StoneButton {
                        label: "Filter"
                        width: 96
                        height: 40
                        onActivated: scene.categoryRequested()
                    }
                    StoneButton {
                        objectName: "librarySelectButton"
                        label: scene.selectionMode ? "Done" : "Select"
                        width: 88
                        height: 40
                        onActivated: {
                            if (scene.selectionMode) scene.finishSelection()
                            else scene.selectionMode = true
                        }
                    }
                    StoneButton {
                        label: "Import Media"
                        enabled: !scene.appBridge.importBusy
                        width: 135
                        height: 40
                        onActivated: scene.importRequested()
                    }
                }
                Flow {
                    visible: scene.selectionMode
                    width: parent.width
                    height: visible ? childrenRect.height : 0
                    spacing: 12
                    Text {
                        text: scene.selectedOwners.length ? scene.selectedOwners.length + " selected" : "Select items"
                        color: theme.muted
                        font.pixelSize: 14
                        height: 40
                        verticalAlignment: Text.AlignVCenter
                    }
                    StoneButton {
                        objectName: "librarySelectionActionsButton"
                        visible: scene.selectedOwners.length > 0
                        label: "Actions…"
                        width: 175
                        height: 40
                        onActivated: selectionActions.open()
                    }
                }
                Flow {
                    id: mediaFlow
                    objectName: "libraryMediaFlow"
                    width: parent.width
                    height: Math.max(0, totalRows * rowStride - spacing)
                    spacing: 14
                    readonly property int columns: Math.max(1, Math.min(5, Math.floor((width + 14) / 200)))
                    readonly property real cardWidth: (width - 14 * (columns - 1)) / columns
                    readonly property real cardHeight: cardWidth * 9 / 16 + 170
                    readonly property real rowStride: cardHeight + spacing
                    readonly property int totalRows: Math.ceil(scene.media.length / columns)
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
                        objectName: "libraryMediaRepeater"
                        model: scene.route === "home"
                            ? scene.media.slice(0, mediaFlow.columns)
                            : scene.media.slice(mediaFlow.firstRow * mediaFlow.columns,
                                                mediaFlow.lastRow * mediaFlow.columns)
                        StoneField {
                            required property var modelData
                            width: mediaFlow.cardWidth
                            height: mediaFlow.cardHeight
                            interactive: true
                            accessibilityLabel: "Details for " + modelData.title
                            onActivated: {
                                if (scene.selectionMode) scene.toggleSelection(modelData.owner)
                                else scene.appBridge.openLibraryDetails(modelData.owner)
                            }
                            Image {
                                x: 4; y: 4
                                width: parent.width - 8
                                height: parent.width * 9 / 16
                                source: scene.appBridge.mediaArtwork(modelData.owner)
                                fillMode: Image.PreserveAspectCrop
                                visible: source.toString().length > 0
                                smooth: true
                            }
                            StoneButton {
                                visible: scene.selectionMode
                                x: 7; y: 7
                                width: 30; height: 30
                                label: scene.selectedOwners.indexOf(modelData.owner) >= 0 ? "✓" : ""
                                accessibilityLabel: "Select " + modelData.title
                                selected: scene.selectedOwners.indexOf(modelData.owner) >= 0
                                onActivated: scene.toggleSelection(modelData.owner)
                            }
                            Column {
                                x: 10; y: parent.width * 9 / 16 + 10
                                width: parent.width - 20
                                spacing: 3
                                Text { text: modelData.title; color: theme.text; font.pixelSize: 14; font.bold: true; width: parent.width; elide: Text.ElideRight }
                                Text { text: modelData.creator; color: theme.muted; font.pixelSize: 12; width: parent.width; elide: Text.ElideRight }
                                Text { text: modelData.type; color: theme.muted; font.pixelSize: 12 }
                                Row {
                                    spacing: 5
                                    StoneButton { label: "Play"; size: "inline"; width: 78; onActivated: scene.appBridge.openLibraryOwner(modelData.owner) }
                                    StoneButton { label: "More"; size: "inline"; width: 72; onActivated: scene.actionsRequested(modelData.owner) }
                                }
                            }
                        }
                    }
                    Item {
                        visible: mediaFlow.lastRow < mediaFlow.totalRows
                        width: mediaFlow.width
                        height: Math.max(0, (mediaFlow.totalRows - mediaFlow.lastRow) * mediaFlow.rowStride - mediaFlow.spacing)
                    }
                }
                LibraryEmptyPanel {
                    objectName: "libraryMediaEmptyPanel"
                    visible: scene.media.length === 0 && ["channels", "playlists", "collections"].indexOf(scene.route) < 0
                    width: parent.width
                    filtered: scene.appBridge.librarySearch.length > 0 || scene.appBridge.libraryCategory !== "All categories" || scene.route === "group"
                    actions: scene.route !== "home" || scene.counts.all > 0 || filtered
                    onForgeRequested: scene.appBridge.select("Forge")
                    onImportRequested: scene.importRequested()
                    onClearRequested: {
                        scene.appBridge.setLibrarySearch("")
                        scene.appBridge.setLibraryCategory("All categories")
                        scene.appBridge.navigateLibrary("all")
                    }
                }
                Item { width: 1; height: 20 }
            }
            Popup {
                id: selectionActions
                objectName: "librarySelectionActionsPopup"
                x: Math.max(0, (scene.width - width) / 2)
                y: Math.max(0, (scene.height - height) / 2)
                width: Math.min(260, scene.width - 24)
                height: 150
                padding: 5
                background: StoneField {}
                Column {
                    anchors.fill: parent
                    spacing: 2
                    Repeater {
                        model: [
                            { label: "Add to Collection…", action: "collection" },
                            { label: "Move to…", action: "move" },
                            { label: "Delete…", action: "delete" }
                        ]
                        StoneButton {
                            required property var modelData
                            width: parent.width; height: 44
                            label: modelData.label
                            onActivated: {
                                var owners = scene.selectedOwners.slice()
                                selectionActions.close()
                                scene.selectionActionRequested(modelData.action, owners)
                            }
                        }
                    }
                    Item {
                        visible: groupFlow.lastRow < groupFlow.totalRows
                        width: groupFlow.width
                        height: Math.max(0, (groupFlow.totalRows - groupFlow.lastRow) * groupFlow.rowStride - groupFlow.spacing)
                    }
                }
            }
            Popup {
                id: sortPopup
                x: Math.max(0, scene.width - width - 180)
                y: 180
                width: 190
                padding: 8
                modal: true
                background: StoneField {}
                Column {
                    width: parent.width
                    spacing: 5
                    StoneButton { label: "Recently Added"; width: parent.width; height: 38; onActivated: { scene.appBridge.setLibrarySort("recent"); sortPopup.close() } }
                    StoneButton { label: "Title"; width: parent.width; height: 38; onActivated: { scene.appBridge.setLibrarySort("title"); sortPopup.close() } }
                }
            }
            Popup {
                id: storagePopup
                x: 0
                y: Math.max(0, scene.height - height - 140)
                width: 226
                padding: 8
                modal: true
                background: StoneField {}
                Column {
                    width: parent.width
                    spacing: 5
                    Repeater {
                        model: scene.appBridge.storageChoices
                        StoneButton {
                            required property var modelData
                            label: modelData.label
                            width: parent.width
                            height: 38
                            onActivated: { scene.appBridge.selectStorageVolume(modelData.path); storagePopup.close() }
                        }
                    }
                    StoneButton { label: "Refresh storage"; width: parent.width; height: 38; onActivated: { scene.appBridge.refreshStorage(); storagePopup.close() } }
                }
            }
        }
    }
    Popup {
        id: groupMenu
        objectName: "libraryGroupMenu"
        x: scene.groupMenuX
        y: scene.groupMenuY
        width: 200
        height: 100
        padding: 3
        background: StoneField {}
        Column {
            anchors.fill: parent
            spacing: 3
            StoneButton {
                objectName: "libraryGroupOpenButton"
                width: parent.width; height: 44
                label: "Open " + (scene.groupMenuKind === "channel" ? "channel" : scene.groupMenuKind)
                onActivated: {
                    const group = scene.currentMenuGroup()
                    groupMenu.close()
                    if (group) scene.appBridge.navigateLibraryGroup(group.kind, group.key)
                }
            }
            StoneButton {
                objectName: "libraryGroupSelectButton"
                width: parent.width; height: 44
                label: "Select media"
                onActivated: {
                    const group = scene.currentMenuGroup()
                    groupMenu.close()
                    if (group) {
                        scene.selectionMode = true
                        scene.selectedOwners = group.owners.slice()
                    }
                }
            }
        }
    }
}
