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
        roundedPicture.paintedReady = false
        if (roundedPicture.loadedSource.toString().length > 0 &&
                (roundedPicture.isImageLoaded(roundedPicture.loadedSource) || roundedPicture.isImageLoading(roundedPicture.loadedSource)))
            roundedPicture.unloadImage(roundedPicture.loadedSource)
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
        adoptedSource = ""
        reducedSource = ""
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
            paintedReady = false
            const context = getContext("2d")
            context.clearRect(0, 0, width, height)
            if (!isImageLoaded(artwork.presentedSource) || picture.sourceSize.width <= 0 || picture.sourceSize.height <= 0)
                return
            const scale = artwork.cover
                ? Math.max(width / picture.sourceSize.width, height / picture.sourceSize.height)
                : Math.min(width / picture.sourceSize.width, height / picture.sourceSize.height)
            const paintedWidth = picture.sourceSize.width * scale
            const paintedHeight = picture.sourceSize.height * scale
            const left = (width - paintedWidth) / 2
            const top = (height - paintedHeight) / 2
            context.save()
            context.beginPath()
            if (artwork.cover) context.roundedRect(0, 0, width, height, 7, 7)
            else context.roundedRect(left, top, paintedWidth, paintedHeight, 7, 7)
            context.clip()
            context.drawImage(artwork.presentedSource, left, top, paintedWidth, paintedHeight)
            context.restore()
            paintedReady = true
        }
    }
}
