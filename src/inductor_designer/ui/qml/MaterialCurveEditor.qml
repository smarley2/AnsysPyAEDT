import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialCurveEditor
    property var controller: null
    property var pointModel: controller !== null ? controller.points : []

    function valueRange(axis) {
        if (pointModel.length === 0) {
            return [0, 1]
        }
        let low = pointModel[0][axis]
        let high = low
        for (let index = 1; index < pointModel.length; ++index) {
            low = Math.min(low, pointModel[index][axis])
            high = Math.max(high, pointModel[index][axis])
        }
        return low === high ? [low, low + 1] : [low, high]
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 6

        Label {
            text: qsTr("Curve and numeric point editor")
            font.bold: true
        }

        Canvas {
            id: curveCanvas
            objectName: "materialCurveCanvas"
            Layout.fillWidth: true
            Layout.preferredHeight: 120
            Accessible.name: qsTr("Current material curve plot")
            onPaint: {
                const context = getContext("2d")
                context.reset()
                context.strokeStyle = palette.mid
                context.strokeRect(0, 0, width, height)
                if (materialCurveEditor.pointModel.length === 0) {
                    return
                }
                const xRange = materialCurveEditor.valueRange("x")
                const yRange = materialCurveEditor.valueRange("y")
                context.strokeStyle = palette.highlight
                context.lineWidth = 2
                context.beginPath()
                for (let index = 0; index < materialCurveEditor.pointModel.length; ++index) {
                    const point = materialCurveEditor.pointModel[index]
                    const x = (point.x - xRange[0]) / (xRange[1] - xRange[0]) * width
                    const y = height - (point.y - yRange[0]) / (yRange[1] - yRange[0]) * height
                    if (index === 0) {
                        context.moveTo(x, y)
                    } else {
                        context.lineTo(x, y)
                    }
                }
                context.stroke()
            }

            Connections {
                target: materialCurveEditor.controller
                function onSelectionChanged() { curveCanvas.requestPaint() }
            }
        }

        ScrollView {
            id: canonicalPointList
            objectName: "canonicalPointList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            Accessible.name: qsTr("Canonical material points")

            ColumnLayout {
                width: canonicalPointList.availableWidth
                Repeater {
                    model: materialCurveEditor.pointModel
                    delegate: RowLayout {
                        required property int index
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 4

                        Label { text: qsTr("%1:").arg(index + 1) }
                        TextField {
                            id: xField
                            objectName: "canonicalPointX-" + index
                            Layout.fillWidth: true
                            text: String(modelData.x)
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Point %1 canonical X value").arg(index + 1)
                        }
                        TextField {
                            id: yField
                            objectName: "canonicalPointY-" + index
                            Layout.fillWidth: true
                            text: String(modelData.y)
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Point %1 canonical Y value").arg(index + 1)
                        }
                        Button {
                            objectName: "applyCanonicalPoint-" + index
                            text: qsTr("Apply")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Apply point %1 numeric values").arg(index + 1)
                            onClicked: materialCurveEditor.controller.setCanonicalPoint(
                                modelData.seriesId,
                                modelData.index,
                                Number(xField.text),
                                Number(yField.text)
                            )
                        }
                        Button {
                            objectName: "deletePoint-" + index
                            text: qsTr("Delete")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Delete point %1").arg(index + 1)
                            onClicked: materialCurveEditor.controller.deletePoint(
                                modelData.index
                            )
                        }
                    }
                }
            }
        }
    }
}
