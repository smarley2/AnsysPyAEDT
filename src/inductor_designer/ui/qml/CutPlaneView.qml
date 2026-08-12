import QtQuick

// The 2D model exactly as FEMM and Maxwell 2D will receive it. Every number
// arrives from `GuidedStudioController.cutPlaneDrawing`; this file only paints.
Item {
    id: root
    objectName: "cutPlaneView"

    property var drawing: ({
        "r_inner_mm": 0.0,
        "r_outer_mm": 0.0,
        "depth_mm": 0.0,
        "extent_mm": 1.0,
        "circles": [],
        "note": ""
    })
    property color background: "#f8f7f4"

    onDrawingChanged: canvas.requestPaint()

    Rectangle {
        anchors.fill: parent
        color: root.background
    }

    Canvas {
        id: canvas
        objectName: "cutPlaneCanvas"
        anchors.fill: parent
        anchors.bottomMargin: 52
        anchors.margins: 20
        renderStrategy: Canvas.Immediate

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()

            var extent = Math.max(root.drawing.extent_mm, 1e-6)
            var scale = Math.min(width, height) / (2 * extent * 1.06)
            var cx = width / 2
            var cy = height / 2

            function px(mm) { return cx + mm * scale }
            function py(mm) { return cy - mm * scale }

            // Annulus: an outer grey disc with the bore painted back out. QML's
            // Canvas fill is non-zero winding, so a two-arc even-odd path is
            // not available.
            ctx.fillStyle = "#b9b6b0"
            ctx.beginPath()
            ctx.arc(cx, cy, root.drawing.r_outer_mm * scale, 0, 2 * Math.PI)
            ctx.fill()
            ctx.fillStyle = root.background
            ctx.beginPath()
            ctx.arc(cx, cy, root.drawing.r_inner_mm * scale, 0, 2 * Math.PI)
            ctx.fill()

            for (var i = 0; i < root.drawing.circles.length; ++i) {
                var c = root.drawing.circles[i]
                var r = Math.max(c.radius_mm * scale, 1.5)
                var x = px(c.x_mm)
                var y = py(c.y_mm)

                ctx.fillStyle = c.color
                ctx.beginPath()
                ctx.arc(x, y, r, 0, 2 * Math.PI)
                ctx.fill()

                ctx.strokeStyle = "#ffffff"
                ctx.fillStyle = "#ffffff"
                ctx.lineWidth = Math.max(r * 0.28, 1)
                if (c.into_plane) {
                    // Cross: current flows away from the viewer.
                    var d = r * 0.5
                    ctx.beginPath()
                    ctx.moveTo(x - d, y - d)
                    ctx.lineTo(x + d, y + d)
                    ctx.moveTo(x + d, y - d)
                    ctx.lineTo(x - d, y + d)
                    ctx.stroke()
                } else {
                    // Dot: current flows towards the viewer.
                    ctx.beginPath()
                    ctx.arc(x, y, Math.max(r * 0.32, 1), 0, 2 * Math.PI)
                    ctx.fill()
                }
            }

            // Scale bar: the outer radius, drawn under the model.
            var barMm = root.drawing.r_outer_mm
            var barPx = barMm * scale
            var barY = height - 10
            ctx.strokeStyle = "#5b5852"
            ctx.lineWidth = 1
            ctx.beginPath()
            ctx.moveTo(cx - barPx / 2, barY)
            ctx.lineTo(cx + barPx / 2, barY)
            ctx.moveTo(cx - barPx / 2, barY - 4)
            ctx.lineTo(cx - barPx / 2, barY + 4)
            ctx.moveTo(cx + barPx / 2, barY - 4)
            ctx.lineTo(cx + barPx / 2, barY + 4)
            ctx.stroke()
            ctx.fillStyle = "#5b5852"
            ctx.font = "11px sans-serif"
            ctx.textAlign = "center"
            ctx.fillText(qsTr("%1 mm").arg(barMm.toFixed(2)), cx, barY - 8)
        }
    }

    Text {
        objectName: "cutPlaneNote"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 12
        wrapMode: Text.WordWrap
        color: "#5b5852"
        font.pixelSize: 12
        text: root.drawing.note
    }
}
