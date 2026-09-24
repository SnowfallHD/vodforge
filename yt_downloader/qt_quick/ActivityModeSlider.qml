import QtQuick

Item {
    id: slider
    objectName: "activityModeSlider"
    width: 30
    height: 116
    implicitWidth: 30
    implicitHeight: 116
    activeFocusOnTab: true
    property bool technical: false
    readonly property int themeRevision: bridge.themeRevision
    signal selected(bool technical)

    Accessible.role: Accessible.Slider
    Accessible.name: "Activity detail level"
    Accessible.description: "Top: friendly progress. Bottom: technical details."

    function choose(value) {
        if (technical !== value)
            selected(value)
    }

    onTechnicalChanged: dial.requestPaint()
    onThemeRevisionChanged: dial.requestPaint()
    onActiveFocusChanged: dial.requestPaint()
    Keys.onUpPressed: choose(false)
    Keys.onDownPressed: choose(true)
    Keys.onSpacePressed: choose(!technical)
    Keys.onReturnPressed: choose(!technical)

    Canvas {
        id: dial
        anchors.fill: parent
        onPaint: {
            const context = getContext("2d")
            context.clearRect(0, 0, width, height)
            context.lineCap = "round"
            for (const state of [{ y: 13, technical: false }, { y: 103, technical: true }]) {
                const color = state.technical === slider.technical ? theme.accent : theme.muted
                context.strokeStyle = color
                context.lineWidth = 1.5
                context.beginPath()
                context.arc(15, state.y, 10, 0, Math.PI * 2)
                context.stroke()
                context.fillStyle = color
                for (const x of [11, 19]) {
                    context.beginPath()
                    context.arc(x, state.y - 2, 1, 0, Math.PI * 2)
                    context.fill()
                }
                context.beginPath()
                if (state.technical)
                    context.arc(15, state.y + 7, 5, Math.PI, Math.PI * 2)
                else
                    context.arc(15, state.y + 1, 5, 0, Math.PI)
                context.stroke()
            }
            context.strokeStyle = theme.surface_2
            context.lineWidth = 5
            context.beginPath()
            context.moveTo(15, 35)
            context.lineTo(15, 81)
            context.stroke()
            context.fillStyle = slider.activeFocus ? theme.text : theme.accent
            context.beginPath()
            context.arc(15, slider.technical ? 78 : 38, 6, 0, Math.PI * 2)
            context.fill()
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed: { slider.forceActiveFocus(); slider.choose(mouse.y >= 58) }
        onPositionChanged: if (pressed) slider.choose(mouse.y >= 58)
    }
}
