import QtQuick

Item {
    id: artwork
    property url source: ""
    // Avatar assets arrive as transparent circular PNGs from QtArtwork.
    property bool circular: false
    property int inset: 4
    readonly property bool hasArtwork: source.toString().length > 0
    visible: hasArtwork
    onSourceChanged: {
        roundedPicture.paintedReady = false
        if (roundedPicture.loadedSource.toString().length > 0 &&
                (roundedPicture.isImageLoaded(roundedPicture.loadedSource) ||
                 roundedPicture.isImageLoading(roundedPicture.loadedSource)))
            roundedPicture.unloadImage(roundedPicture.loadedSource)
        roundedPicture.loadedSource = source
        if (hasArtwork && !circular) roundedPicture.loadImage(source)
        roundedPicture.requestPaint()
    }

    Image {
        id: picture
        anchors.fill: parent
        anchors.margins: artwork.inset
        source: artwork.source
        fillMode: Image.PreserveAspectFit
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
        onVisibleChanged: {
            if (visible && artwork.hasArtwork && !isImageLoaded(artwork.source) && !isImageLoading(artwork.source))
                loadImage(artwork.source)
        }
        onImageLoaded: requestPaint()
        onWidthChanged: { paintedReady = false; requestPaint() }
        onHeightChanged: { paintedReady = false; requestPaint() }
        onPaint: {
            paintedReady = false
            const context = getContext("2d")
            context.clearRect(0, 0, width, height)
            if (!isImageLoaded(artwork.source) || picture.sourceSize.width <= 0 || picture.sourceSize.height <= 0)
                return
            const scale = Math.min(width / picture.sourceSize.width, height / picture.sourceSize.height)
            const paintedWidth = picture.sourceSize.width * scale
            const paintedHeight = picture.sourceSize.height * scale
            const left = (width - paintedWidth) / 2
            const top = (height - paintedHeight) / 2
            context.save()
            context.beginPath()
            context.roundedRect(left, top, paintedWidth, paintedHeight, 7, 7)
            context.clip()
            context.drawImage(artwork.source, left, top, paintedWidth, paintedHeight)
            context.restore()
            paintedReady = true
        }
    }
}
