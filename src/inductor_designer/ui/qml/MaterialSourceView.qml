import QtQuick
import QtQuick.Controls

Item {
    id: materialSourceView
    property var controller: null
    property var sourceData: controller !== null ? controller.source : ({})
    property var editing: controller !== null ? controller.imageEditing : ({})
    property real sourceWidth: sourceData.width || 1
    property real sourceHeight: sourceData.height || 1
    property real sourceScale: Math.min(width / sourceWidth, height / sourceHeight)
    property real sourceOffsetX: (width - sourceWidth * sourceScale) / 2
    property real sourceOffsetY: (height - sourceHeight * sourceScale) / 2

    Accessible.name: qsTr("Manual material source digitization")
    Accessible.description: qsTr(
        "Click the displayed source to add a manual point. Coordinates are stored in original source pixels."
    )

    function originalX(displayX) {
        return (displayX - sourceOffsetX) / sourceScale
    }

    function originalY(displayY) {
        return (displayY - sourceOffsetY) / sourceScale
    }

    function displayX(originalX) {
        return sourceOffsetX + originalX * sourceScale
    }

    function displayY(originalY) {
        return sourceOffsetY + originalY * sourceScale
    }

    function clamp(value, low, high) {
        return Math.max(low, Math.min(value, high))
    }

    function setCropTopLeft(originalX, originalY) {
        const crop = editing.crop || ({})
        const right = Math.round(clamp(crop.left + crop.width, 1, sourceWidth))
        const bottom = Math.round(clamp(crop.top + crop.height, 1, sourceHeight))
        const left = Math.round(clamp(originalX, 0, Math.max(0, right - 1)))
        const top = Math.round(clamp(originalY, 0, Math.max(0, bottom - 1)))
        controller.setCrop(left, top, right - left, bottom - top)
    }

    function setCropBottomRight(originalX, originalY) {
        const crop = editing.crop || ({})
        const left = Math.round(clamp(crop.left, 0, sourceWidth - 1))
        const top = Math.round(clamp(crop.top, 0, sourceHeight - 1))
        const right = Math.round(clamp(originalX, left + 1, sourceWidth))
        const bottom = Math.round(clamp(originalY, top + 1, sourceHeight))
        controller.setCrop(left, top, right - left, bottom - top)
    }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        border.color: materialSourceView.activeFocus ? palette.highlight : palette.mid
        border.width: materialSourceView.activeFocus ? 3 : 1
    }

    Image {
        id: sourceImage
        objectName: "materialSourceImage"
        x: materialSourceView.sourceOffsetX
        y: materialSourceView.sourceOffsetY
        width: materialSourceView.sourceWidth * materialSourceView.sourceScale
        height: materialSourceView.sourceHeight * materialSourceView.sourceScale
        source: materialSourceView.sourceData.dataUrl || ""
        fillMode: Image.Stretch
        asynchronous: false
    }

    Canvas {
        id: sourceOverlay
        anchors.fill: parent
        onPaint: {
            const context = getContext("2d")
            context.reset()
            const crop = materialSourceView.editing.crop || ({})
            if (crop.width > 0 && crop.height > 0) {
                context.strokeStyle = palette.highlight
                context.lineWidth = 2
                context.setLineDash([7, 4])
                context.strokeRect(
                    materialSourceView.displayX(crop.left),
                    materialSourceView.displayY(crop.top),
                    crop.width * materialSourceView.sourceScale,
                    crop.height * materialSourceView.sourceScale
                )
                context.setLineDash([])
            }
            const points = materialSourceView.editing.pixelPoints || []
            context.fillStyle = palette.highlight
            context.strokeStyle = palette.windowText
            for (let index = 0; index < points.length; ++index) {
                const point = points[index]
                context.beginPath()
                context.arc(
                    materialSourceView.displayX(point.xPx),
                    materialSourceView.displayY(point.yPx),
                    5,
                    0,
                    Math.PI * 2
                )
                context.fill()
                context.stroke()
            }
        }

        Connections {
            target: materialSourceView.controller
            function onSourceChanged() { sourceOverlay.requestPaint() }
        }
    }

    Repeater {
        model: materialSourceView.editing.pixelPoints || []
        delegate: Rectangle {
            id: sourcePointHandle
            required property int index
            required property var modelData
            objectName: "sourcePointHandle-" + index
            width: 16
            height: 16
            radius: 8
            color: "transparent"
            border.color: activeFocus ? palette.highlight : palette.windowText
            border.width: activeFocus ? 4 : 2
            x: materialSourceView.displayX(modelData.xPx) - width / 2
            y: materialSourceView.displayY(modelData.yPx) - height / 2
            activeFocusOnTab: true
            Accessible.name: qsTr("Move source point %1").arg(index + 1)
            Accessible.description: qsTr(
                "Drag the point or use the arrow keys; stored coordinates remain in original source pixels."
            )

            function moveBy(deltaX, deltaY) {
                materialSourceView.controller.movePixelPoint(
                    index,
                    modelData.xPx + deltaX,
                    modelData.yPx + deltaY
                )
            }

            Keys.onLeftPressed: moveBy(-1, 0)
            Keys.onRightPressed: moveBy(1, 0)
            Keys.onUpPressed: moveBy(0, -1)
            Keys.onDownPressed: moveBy(0, 1)

            DragHandler {
                target: sourcePointHandle
                onActiveChanged: {
                    if (!active && materialSourceView.controller !== null) {
                        materialSourceView.controller.movePixelPoint(
                            sourcePointHandle.index,
                            materialSourceView.originalX(
                                sourcePointHandle.x + sourcePointHandle.width / 2
                            ),
                            materialSourceView.originalY(
                                sourcePointHandle.y + sourcePointHandle.height / 2
                            )
                        )
                    }
                }
            }
        }
    }

    Rectangle {
        id: cropHandleTopLeft
        objectName: "cropHandleTopLeft"
        visible: (materialSourceView.editing.crop || ({})).width > 0
        width: 14
        height: 14
        color: palette.highlight
        border.color: palette.windowText
        border.width: activeFocus ? 4 : 2
        x: materialSourceView.displayX((materialSourceView.editing.crop || ({})).left || 0) - width / 2
        y: materialSourceView.displayY((materialSourceView.editing.crop || ({})).top || 0) - height / 2
        activeFocusOnTab: true
        Accessible.name: qsTr("Crop top-left handle")
        Accessible.description: qsTr(
            "Drag the crop corner or use arrow keys; coordinates use original source pixels."
        )

        function moveBy(deltaX, deltaY) {
            const crop = materialSourceView.editing.crop || ({})
            materialSourceView.setCropTopLeft(
                crop.left + deltaX, crop.top + deltaY
            )
        }

        Keys.onLeftPressed: moveBy(-1, 0)
        Keys.onRightPressed: moveBy(1, 0)
        Keys.onUpPressed: moveBy(0, -1)
        Keys.onDownPressed: moveBy(0, 1)

        DragHandler {
            target: null
            onActiveChanged: {
                if (!active && materialSourceView.controller !== null) {
                    const point = cropHandleTopLeft.mapToItem(
                        materialSourceView, centroid.position.x, centroid.position.y
                    )
                    materialSourceView.setCropTopLeft(
                        materialSourceView.originalX(point.x),
                        materialSourceView.originalY(point.y)
                    )
                }
            }
        }
    }

    Rectangle {
        id: cropHandleBottomRight
        objectName: "cropHandleBottomRight"
        visible: cropHandleTopLeft.visible
        width: 14
        height: 14
        color: palette.highlight
        border.color: palette.windowText
        border.width: activeFocus ? 4 : 2
        x: {
            const crop = materialSourceView.editing.crop || ({})
            return materialSourceView.displayX((crop.left || 0) + (crop.width || 0)) - width / 2
        }
        y: {
            const crop = materialSourceView.editing.crop || ({})
            return materialSourceView.displayY((crop.top || 0) + (crop.height || 0)) - height / 2
        }
        activeFocusOnTab: true
        Accessible.name: qsTr("Crop bottom-right handle")
        Accessible.description: qsTr(
            "Drag the crop corner or use arrow keys; coordinates use original source pixels."
        )

        function moveBy(deltaX, deltaY) {
            const crop = materialSourceView.editing.crop || ({})
            materialSourceView.setCropBottomRight(
                crop.left + crop.width + deltaX,
                crop.top + crop.height + deltaY
            )
        }

        Keys.onLeftPressed: moveBy(-1, 0)
        Keys.onRightPressed: moveBy(1, 0)
        Keys.onUpPressed: moveBy(0, -1)
        Keys.onDownPressed: moveBy(0, 1)

        DragHandler {
            target: null
            onActiveChanged: {
                if (!active && materialSourceView.controller !== null) {
                    const point = cropHandleBottomRight.mapToItem(
                        materialSourceView, centroid.position.x, centroid.position.y
                    )
                    materialSourceView.setCropBottomRight(
                        materialSourceView.originalX(point.x),
                        materialSourceView.originalY(point.y)
                    )
                }
            }
        }
    }

    Repeater {
        model: [
            ["xAxisAnchorA", qsTr("X axis anchor A"), "xAxis", "pixelA", 0],
            ["xAxisAnchorB", qsTr("X axis anchor B"), "xAxis", "pixelB", 0],
            ["yAxisAnchorA", qsTr("Y axis anchor A"), "yAxis", "pixelA", 1],
            ["yAxisAnchorB", qsTr("Y axis anchor B"), "yAxis", "pixelB", 1]
        ]
        delegate: Rectangle {
            id: axisHandle
            required property var modelData
            objectName: modelData[0]
            width: 12
            height: 12
            radius: 6
            color: "transparent"
            border.color: palette.highlight
            border.width: activeFocus ? 5 : 3
            x: modelData[4] === 0
                ? materialSourceView.displayX(
                    ((materialSourceView.editing[modelData[2]] || ({}))[modelData[3]]) || 0
                ) - width / 2
                : materialSourceView.sourceOffsetX - width / 2
            y: modelData[4] === 1
                ? materialSourceView.displayY(
                    ((materialSourceView.editing[modelData[2]] || ({}))[modelData[3]]) || 0
                ) - height / 2
                : materialSourceView.sourceOffsetY + materialSourceView.sourceHeight
                    * materialSourceView.sourceScale - height / 2
            activeFocusOnTab: true
            Accessible.name: modelData[1]
            Accessible.description: qsTr(
                "Drag the axis anchor or use arrow keys; coordinates use original source pixels."
            )

            function setPixel(pixel) {
                const axis = materialSourceView.editing[modelData[2]] || ({})
                const bounded = materialSourceView.clamp(
                    pixel,
                    0,
                    modelData[4] === 0
                        ? materialSourceView.sourceWidth
                        : materialSourceView.sourceHeight
                )
                const pixelA = modelData[3] === "pixelA" ? bounded : axis.pixelA
                const pixelB = modelData[3] === "pixelB" ? bounded : axis.pixelB
                if (modelData[2] === "xAxis") {
                    materialSourceView.controller.setXAxis(
                        axis.scale,
                        pixelA,
                        axis.valueA,
                        pixelB,
                        axis.valueB
                    )
                } else {
                    materialSourceView.controller.setYAxis(
                        axis.scale,
                        pixelA,
                        axis.valueA,
                        pixelB,
                        axis.valueB
                    )
                }
            }

            function moveBy(delta) {
                const axis = materialSourceView.editing[modelData[2]] || ({})
                setPixel(axis[modelData[3]] + delta)
            }

            Keys.onLeftPressed: if (modelData[4] === 0) moveBy(-1)
            Keys.onRightPressed: if (modelData[4] === 0) moveBy(1)
            Keys.onUpPressed: if (modelData[4] === 1) moveBy(-1)
            Keys.onDownPressed: if (modelData[4] === 1) moveBy(1)

            DragHandler {
                target: null
                onActiveChanged: {
                    if (!active && materialSourceView.controller !== null) {
                        const point = axisHandle.mapToItem(
                            materialSourceView, centroid.position.x, centroid.position.y
                        )
                        axisHandle.setPixel(
                            axisHandle.modelData[4] === 0
                                ? materialSourceView.originalX(point.x)
                                : materialSourceView.originalY(point.y)
                        )
                    }
                }
            }
        }
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        onTapped: function(eventPoint) {
            const originalX = materialSourceView.originalX(eventPoint.position.x)
            const originalY = materialSourceView.originalY(eventPoint.position.y)
            if (originalX >= 0 && originalX <= materialSourceView.sourceWidth
                    && originalY >= 0 && originalY <= materialSourceView.sourceHeight
                    && materialSourceView.controller !== null) {
                materialSourceView.controller.addPixelPoint(originalX, originalY)
            }
        }
    }
}
