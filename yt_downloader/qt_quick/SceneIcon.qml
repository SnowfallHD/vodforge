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
        } else if (name === "download") {
            line([[.5, 0], [.5, .70]])
            line([[.25, .45], [.5, .70], [.75, .45]])
            line([[0, .65], [0, 1], [1, 1], [1, .65]])
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
        } else if (name === "play") {
            line([[.25, .12], [.82, .5], [.25, .88], [.25, .12]])
        } else if (name === "pause") {
            line([[.28, .14], [.28, .86]])
            line([[.72, .14], [.72, .86]])
        } else if (name === "backward") {
            line([[.30, .15], [.06, .15], [.06, .40]])
            c.beginPath(); c.arc(.50 * s, .53 * s, .39 * s, 3.8, 7.8); c.stroke()
            c.font = "bold " + Math.round(s * .38) + "px sans-serif"
            c.textAlign = "center"; c.fillText("10", .51 * s, .66 * s)
        } else if (name === "forward") {
            line([[.70, .15], [.94, .15], [.94, .40]])
            c.beginPath(); c.arc(.50 * s, .53 * s, .39 * s, 1.9, 6.2); c.stroke()
            c.font = "bold " + Math.round(s * .38) + "px sans-serif"
            c.textAlign = "center"; c.fillText("10", .51 * s, .66 * s)
        } else if (name === "volume" || name === "muted") {
            line([[.06, .37], [.27, .37], [.51, .14], [.51, .86], [.27, .63], [.06, .63], [.06, .37]])
            if (name === "muted") {
                line([[.67, .32], [.93, .68]])
                line([[.93, .32], [.67, .68]])
            } else {
                c.beginPath(); c.arc(.50 * s, .50 * s, .35 * s, -.8, .8); c.stroke()
            }
        } else if (name === "captions") {
            c.strokeRect(.08 * s, .18 * s, .84 * s, .64 * s)
            line([[.40, .43], [.30, .39], [.22, .48], [.30, .59], [.40, .55]])
            line([[.78, .43], [.68, .39], [.60, .48], [.68, .59], [.78, .55]])
        } else if (name === "fullscreen") {
            line([[.08, .37], [.08, .08], [.37, .08]])
            line([[.63, .08], [.92, .08], [.92, .37]])
            line([[.08, .63], [.08, .92], [.37, .92]])
            line([[.63, .92], [.92, .92], [.92, .63]])
        } else if (name === "floating") {
            c.strokeRect(.08 * s, .15 * s, .84 * s, .70 * s)
            c.fillRect(.47 * s, .49 * s, .37 * s, .28 * s)
        } else if (name === "settings") {
            oval(.16, .16, .68, .68, false)
            oval(.40, .40, .20, .20, false)
            for (const [x1, y1, x2, y2] of [[.5,0,.5,.15],[.5,.85,.5,1],[0,.5,.15,.5],[.85,.5,1,.5]])
                line([[x1,y1],[x2,y2]])
        } else if (name === "fit") {
            line([[.08, .40], [.08, .08], [.40, .08]])
            line([[.60, .08], [.92, .08], [.92, .40]])
            line([[.08, .60], [.08, .92], [.40, .92]])
            line([[.60, .92], [.92, .92], [.92, .60]])
        }
    }
}
