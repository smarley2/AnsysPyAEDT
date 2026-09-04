import QtQuick

// The 2D model exactly as FEMM and Maxwell 2D will receive it. Every number
// arrives from `GuidedStudioController.cutPlaneDrawing`; this file only paints.
Item {
    id: root
    objectName: "cutPlaneView"

    property var drawing: ({
        "outline": [],
        "depth_mm": 0.0,
        "extent_mm": 1.0,
        "circles": [],
        "starts": [],
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

            // The bottom 24 px are the scale bar's own band: the model is
            // scaled and centred inside what is left, so a winding covering
            // nearly the whole circumference still cannot reach the bar.
            var barBand = 24
            var usable = height - barBand
            var extent = Math.max(root.drawing.extent_mm, 1e-6)
            var scale = Math.min(width, usable) / (2 * extent * 1.06)
            var cx = width / 2
            var cy = usable / 2

            function px(mm) { return cx + mm * scale }
            function py(mm) { return cy - mm * scale }

            // The core's cross-section, painted in the order the drawing
            // lists it: a `cutout` shape paints the background back over what
            // came before, which is how the toroid's bore has always been
            // drawn and how an E core's gaps are drawn now. QML's Canvas fill
            // is non-zero winding, so an even-odd path is not available.
            for (var s = 0; s < root.drawing.outline.length; ++s) {
                var shape = root.drawing.outline[s]
                ctx.fillStyle = shape.cutout ? root.background : "#b9b6b0"
                ctx.beginPath()
                if (shape.radius_mm !== undefined) {
                    ctx.arc(px(shape.x_mm), py(shape.y_mm),
                            shape.radius_mm * scale, 0, 2 * Math.PI)
                } else {
                    ctx.rect(px(shape.x_mm) - shape.width_mm * scale / 2,
                             py(shape.y_mm) - shape.height_mm * scale / 2,
                             shape.width_mm * scale, shape.height_mm * scale)
                }
                ctx.fill()
            }

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

            // Start markers: a ringed dot at the end each winding is fed in
            // from, the same point the 3D preview beads. Drawn after the
            // conductors so it is never buried under one.
            for (var s = 0; s < root.drawing.starts.length; ++s) {
                var m = root.drawing.starts[s]
                var mr = Math.max(m.radius_mm * scale, 2)
                ctx.fillStyle = m.color
                ctx.beginPath()
                ctx.arc(px(m.x_mm), py(m.y_mm), mr, 0, 2 * Math.PI)
                ctx.fill()
                ctx.strokeStyle = "#2f2c28"
                ctx.lineWidth = Math.max(mr * 0.3, 1)
                ctx.beginPath()
                ctx.arc(px(m.x_mm), py(m.y_mm), mr * 1.6, 0, 2 * Math.PI)
                ctx.stroke()
            }

            // Scale bar: the outer diameter, drawn in the reserved band. It is
            // never wider than the model it sits under, so it always fits.
            // The scale bar spans the drawing, whatever shape the core is.
            var barMm = 2 * root.drawing.extent_mm
            var barPx = barMm * scale
            var barY = usable + barBand - 5
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
