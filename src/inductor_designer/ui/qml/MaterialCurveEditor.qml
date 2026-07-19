import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialCurveEditor
    objectName: "materialCurveEditor"
    property var controller: null
    property var pointModel: controller !== null ? controller.points : []
    property var sourcePointModel: controller !== null ? controller.sourcePoints : []
    property var pendingCanonicalPoints: ({})

    function pointKey(point) {
        return point.seriesId + ":" + point.index
    }

    function pointText(points) {
        return points.map(function(point) {
            return qsTr("%1: %2, %3").arg(point.index + 1).arg(point.x).arg(point.y)
        }).join("; ")
    }

    function pendingText(point, axis) {
        const pending = pendingCanonicalPoints[pointKey(point)]
        return pending !== undefined ? pending[axis] : String(point[axis])
    }

    function setPendingText(point, axis, value) {
        const key = pointKey(point)
        const next = Object.assign({}, pendingCanonicalPoints)
        const entry = Object.assign({
            "x": String(point.x),
            "y": String(point.y)
        }, next[key] || ({}))
        entry[axis] = value
        next[key] = entry
        pendingCanonicalPoints = next
        controller.invalidateEditorInput(
            "canonical:" + key,
            qsTr("Apply or correct the visible canonical point values before saving.")
        )
    }

    function clearPending(point) {
        const next = Object.assign({}, pendingCanonicalPoints)
        delete next[pointKey(point)]
        pendingCanonicalPoints = next
    }

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
                function onEditorReset() {
                    materialCurveEditor.pendingCanonicalPoints = ({})
                }
            }
        }

        Label {
            objectName: "sourcePointComparison"
            Layout.fillWidth: true
            text: materialCurveEditor.controller !== null
                    && materialCurveEditor.controller.sourceComparisonAvailable
                ? qsTr("Source points: %1").arg(
                    materialCurveEditor.pointText(materialCurveEditor.sourcePointModel)
                )
                : qsTr("Source points: no stored source comparison is available")
            wrapMode: Text.WordWrap
            activeFocusOnTab: true
            Accessible.name: text
        }
        Label {
            objectName: "currentPointComparison"
            Layout.fillWidth: true
            text: qsTr("Current points: %1").arg(
                materialCurveEditor.pointText(materialCurveEditor.pointModel)
            )
            wrapMode: Text.WordWrap
            activeFocusOnTab: true
            Accessible.name: text
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
                            property bool parseValid: text.trim().length > 0
                                && Number.isFinite(Number(text))
                            text: materialCurveEditor.pendingText(modelData, "x")
                            validator: DoubleValidator {
                                notation: DoubleValidator.ScientificNotation
                            }
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            onTextEdited: materialCurveEditor.setPendingText(
                                modelData, "x", text
                            )
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Point %1 canonical X value").arg(index + 1)
                        }
                        TextField {
                            id: yField
                            objectName: "canonicalPointY-" + index
                            Layout.fillWidth: true
                            property bool parseValid: text.trim().length > 0
                                && Number.isFinite(Number(text))
                            text: materialCurveEditor.pendingText(modelData, "y")
                            validator: DoubleValidator {
                                notation: DoubleValidator.ScientificNotation
                            }
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            onTextEdited: materialCurveEditor.setPendingText(
                                modelData, "y", text
                            )
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Point %1 canonical Y value").arg(index + 1)
                        }
                        Button {
                            objectName: "applyCanonicalPoint-" + index
                            text: qsTr("Apply")
                            enabled: xField.parseValid && yField.parseValid
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Apply point %1 numeric values").arg(index + 1)
                            onClicked: {
                                const editor = materialCurveEditor
                                const point = modelData
                                if (editor.controller.setCanonicalPoint(
                                        modelData.seriesId,
                                        modelData.index,
                                        Number(xField.text),
                                        Number(yField.text))) {
                                    editor.clearPending(point)
                                }
                            }
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
