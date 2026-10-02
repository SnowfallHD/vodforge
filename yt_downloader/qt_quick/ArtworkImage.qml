import QtQuick
import QtQuick.Controls

Item {
    id: artwork
    property url source: ""
    // Avatar assets arrive as transparent circular PNGs from QtArtwork.
    // Only settled geometry admits a derived image; continuous resizing retains
    // the last ready reduction. The provider performs decoding off the UI thread.
    property url reducedSource: ""
    property url adoptedSource: ""
    readonly property url presentedSource: circular || !adoptedSource.toString().length ? source : adoptedSource
    function scheduleReduction() { reductionDebounce.restart() }
    onWidthChanged: scheduleReduction()
    onHeightChanged: scheduleReduction()
    onCoverChanged: scheduleReduction()
    onInsetChanged: scheduleReduction()
    onCircularChanged: scheduleReduction()
    property real artworkDpr: Screen.devicePixelRatio
    onArtworkDprChanged: scheduleReduction()
    Timer {
        id: reductionDebounce
        interval: 80
        onTriggered: {
            if (artwork.circular || !artwork.hasArtwork) return
            const w = Math.max(1, Math.round((artwork.width - 2 * artwork.inset) * artwork.artworkDpr))
            const h = Math.max(1, Math.round((artwork.height - 2 * artwork.inset) * artwork.artworkDpr))
            artwork.reducedSource = "image://vodforge-thumbnails/source=" + encodeURIComponent(artwork.source.toString()) + "&w=" + w + "&h=" + h + "&cover=" + (artwork.cover ? "1" : "0")
        }
    }
    onPresentedSourceChanged: {
        // Keep the last painted source loaded until the replacement Canvas
        // image is ready, including when resizing clears the backing texture.
        if (roundedPicture.loadedSource.toString() !== roundedPicture.paintedSource.toString() &&
                roundedPicture.loadedSource.toString() !== presentedSource.toString())
            roundedPicture.discardSource(roundedPicture.loadedSource)
        roundedPicture.loadedSource = presentedSource
        if (hasArtwork && !circular) roundedPicture.loadImage(presentedSource)
        roundedPicture.requestPaint()
    }
    property bool circular: false
    property bool cover: false
    property bool pending: false
    property int inset: 4
    readonly property bool hasArtwork: source.toString().length > 0
    readonly property bool waitingForPaint: hasArtwork &&
        (picture.status === Image.Loading ||
         (picture.status === Image.Ready && !circular && !roundedPicture.paintedReady))
    property bool showDelayedLoading: false
    visible: hasArtwork || pending
    onPendingChanged: { showDelayedLoading = false }
    onSourceChanged: {
        showDelayedLoading = false
        roundedPicture.resetOwner()
        adoptedSource = ""
        reducedSource = ""
        roundedPicture.loadedSource = source
        if (hasArtwork && !circular) roundedPicture.loadImage(source)
        roundedPicture.requestPaint()
        scheduleReduction()
    }
    Timer {
        interval: 300
        running: artwork.pending || artwork.waitingForPaint
        repeat: false
        onTriggered: artwork.showDelayedLoading = true
    }
    BusyIndicator {
        objectName: "delayedArtworkSpinner"
        anchors.centerIn: parent
        width: 28
        height: 28
        visible: artwork.showDelayedLoading && (artwork.pending || artwork.waitingForPaint)
        running: visible
        z: 2
    }

    Image {
        id: reductionCandidate
        source: artwork.circular ? "" : artwork.reducedSource
        asynchronous: true
        cache: false
        visible: false
        onStatusChanged: {
            if (status === Image.Ready) artwork.adoptedSource = source
        }
    }
    Image {
        id: picture
        anchors.fill: parent
        anchors.margins: artwork.inset
        source: artwork.presentedSource
        asynchronous: true
        cache: false
        fillMode: artwork.cover ? Image.PreserveAspectCrop : Image.PreserveAspectFit
        smooth: true
        opacity: artwork.circular ? 1 : 0
        readonly property bool presentationPaintedReady: artwork.circular || roundedPicture.paintedReady
        onStatusChanged: roundedPicture.requestPaint()
    }
    Canvas {
        id: roundedPicture
        property url loadedSource: ""
        property bool paintedReady: false
        property url paintedSource: ""
        property real paintedSourceWidth: 0
        property real paintedSourceHeight: 0
        property bool ownerPaintReady: false
        // A new owner must never display the previous owner's retained pixels.
        opacity: ownerPaintReady ? 1 : 0
        function discardSource(url) {
            if (url.toString().length > 0 && (isImageLoaded(url) || isImageLoading(url)))
                unloadImage(url)
        }
        function resetOwner() {
            discardSource(loadedSource)
            if (paintedSource.toString() !== loadedSource.toString()) discardSource(paintedSource)
            loadedSource = ""
            paintedSource = ""
            paintedSourceWidth = 0
            paintedSourceHeight = 0
            ownerPaintReady = false
            paintedReady = false
        }
        Component.onDestruction: {
            discardSource(loadedSource)
            if (paintedSource.toString() !== loadedSource.toString()) discardSource(paintedSource)
        }
        anchors.fill: picture
        visible: !artwork.circular
        Timer {
            id: resizePaint
            interval: 48
            onTriggered: roundedPicture.requestPaint()
        }
        onVisibleChanged: {
            if (visible && artwork.hasArtwork && !isImageLoaded(artwork.presentedSource) && !isImageLoading(artwork.presentedSource))
                loadImage(artwork.presentedSource)
        }
        onImageLoaded: requestPaint()
        onWidthChanged: { paintedReady = false; resizePaint.restart() }
        onHeightChanged: { paintedReady = false; resizePaint.restart() }
        onPaint: {
            const context = getContext("2d")
            const fresh = isImageLoaded(artwork.presentedSource) && picture.status === Image.Ready &&
                picture.sourceSize.width > 0 && picture.sourceSize.height > 0
            const drawSource = fresh ? artwork.presentedSource : paintedSource
            const sourceWidth = fresh ? picture.sourceSize.width : paintedSourceWidth
            const sourceHeight = fresh ? picture.sourceSize.height : paintedSourceHeight
            if (!drawSource.toString().length || !isImageLoaded(drawSource) || sourceWidth <= 0 || sourceHeight <= 0) {
                context.clearRect(0, 0, width, height)
                ownerPaintReady = false
                paintedReady = false
                return
            }
            context.clearRect(0, 0, width, height)
            const scale = artwork.cover
                ? Math.max(width / sourceWidth, height / sourceHeight)
                : Math.min(width / sourceWidth, height / sourceHeight)
            const paintedWidth = sourceWidth * scale
            const paintedHeight = sourceHeight * scale
            const left = (width - paintedWidth) / 2
            const top = (height - paintedHeight) / 2
            context.save()
            context.beginPath()
            if (artwork.cover) context.roundedRect(0, 0, width, height, 7, 7)
            else context.roundedRect(left, top, paintedWidth, paintedHeight, 7, 7)
            context.clip()
            context.drawImage(drawSource, left, top, paintedWidth, paintedHeight)
            context.restore()
            if (fresh && paintedSource.toString() !== artwork.presentedSource.toString()) {
                const previous = paintedSource
                paintedSource = artwork.presentedSource
                paintedSourceWidth = sourceWidth
                paintedSourceHeight = sourceHeight
                discardSource(previous)
            }
            ownerPaintReady = true
            paintedReady = true
        }
    }
}
