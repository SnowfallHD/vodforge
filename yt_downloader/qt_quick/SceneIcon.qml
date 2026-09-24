import QtQuick

Canvas {
    id: icon
    property string name: ""
    property color tone: theme.icon
    width: 22
    height: 22
    onNameChanged: requestPaint()
    onToneChanged: requestPaint()

    onPaint: {
        const c = getContext("2d")
        c.clearRect(0, 0, width, height)
        const s = Math.min(width, height)
        c.strokeStyle = tone
        c.fillStyle = tone
        c.lineWidth = 2
        c.lineJoin = "round"
        c.lineCap = "round"
        function line(points) {
            c.beginPath()
            c.moveTo(points[0][0] * s, points[0][1] * s)
            for (let i = 1; i < points.length; i++)
                c.lineTo(points[i][0] * s, points[i][1] * s)
            c.stroke()
        }
        function oval(x, y, w, h, filled) {
            c.beginPath()
            c.ellipse(x * s, y * s, w * s, h * s, 0, 0, 2 * Math.PI)
            if (filled) c.fill(); else c.stroke()
        }
        if (name === "folder") {
            line([[0, .22], [.35, .22], [.48, .38], [1, .38], [1, .94], [0, .94], [0, .22]])
        } else if (name === "channels") {
            oval(.32, .08, .36, .36, false)
            oval(.02, .25, .25, .25, false)
            oval(.72, .25, .25, .25, false)
            line([[.22, .94], [.22, .68], [.35, .55], [.65, .55], [.78, .68], [.78, .94]])
            line([[0, .90], [0, .64], [.19, .60]])
            line([[1, .90], [1, .64], [.81, .60]])
        } else if (name === "list") {
            for (const y of [.2, .5, .8]) {
                oval(0, y - .045, .09, .09, true)
                line([[.29, y], [1, y]])
            }
        } else if (name === "videos") {
            c.strokeRect(0, 1, s, s - 2)
            for (const x of [.23, .77]) line([[x, 1 / s], [x, 1 - 1 / s]])
            for (const y of [.28, .5, .72]) {
                line([[0, y], [.23, y]])
                line([[.77, y], [1, y]])
            }
        } else if (name === "audio") {
            line([[.35, .78], [.35, .18], [.87, .05], [.87, .65]])
            line([[.35, .33], [.87, .20]])
            oval(0, .67, .35, .28, false)
            oval(.53, .55, .34, .28, false)
        } else if (name === "plus") {
            line([[.5, 0], [.5, 1]])
            line([[0, .5], [1, .5]])
        } else if (name === "chevron") {
            line([[.35, .15], [.70, .5], [.35, .85]])
        }
    }
}
