import QtQuick

Item {
    id: track
    property real position: 0
    property real duration: 0
    property var chapters: []
    readonly property var segments: {
        if (!(duration > 0)) return []
        return chapters.filter(function(chapter) {
            return isFinite(chapter.start_time) && isFinite(chapter.end_time)
                && chapter.end_time > chapter.start_time && chapter.start_time < duration
        }).map(function(chapter) {
            return {start: Math.max(0, chapter.start_time),
                end: Math.min(duration, chapter.end_time), title: chapter.title || "Untitled chapter"}
        }).filter(function(chapter) { return chapter.end > chapter.start })
    }
    function chapterAt(seconds) {
        for (let i = 0; i < segments.length; ++i)
            if (seconds >= segments[i].start && seconds < segments[i].end)
                return segments[i].title
        return ""
    }
    readonly property string currentChapter: chapterAt(position * duration)
    PlayerTrack {
        anchors.fill: parent
        position: track.position
        visible: track.segments.length === 0
    }
    Repeater {
        model: track.segments
        delegate: Rectangle {
            required property var modelData
            objectName: "playerChapterSegment"
            readonly property real span: (track.width - 10) * (modelData.end - modelData.start) / track.duration
            readonly property real gap: Math.min(2, span * 0.2)
            x: 5 + (track.width - 10) * modelData.start / track.duration + gap / 2
            y: track.height / 2 - 1.5
            width: Math.max(0, span - gap)
            height: 3
            radius: 1.5
            color: theme.border
            Rectangle {
                width: parent.width * Math.max(0, Math.min(1,
                    (track.position * track.duration - modelData.start) / (modelData.end - modelData.start)))
                height: parent.height
                radius: parent.radius
                color: theme.accent
            }
        }
    }
}
