import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialCurveEditor
    objectName: "materialCurveEditor"
    property var controller: null
    property var pointModel: controller !== null ? controller.points : []
    property var importedPointModel: controller !== null ? controller.sourcePoints : []
    property var pendingCanonicalPoints: ({})
    property var activeSeries: {
        if (controller === null) {
            return ({})
        }
        const metadata = (controller.tableEditing || ({})).metadata || ({})
        for (let index = 0; index < controller.series.length; ++index) {
            if (controller.series[index].seriesId === metadata.seriesId) {
                return controller.series[index]
            }
        }
        return controller.series.length > 0 ? controller.series[0] : ({})
    }
    property real plotLeft: 48
    property real plotRight: 12
    property real plotTop: 12
    property real plotBottom: 30

    function pointKey(point) {
        return point.seriesId + ":" + point.index
    }

    function pointText(points) {
        return points.map(function(point) {
            return qsTr("%1: %2, %3").arg(point.index + 1).arg(point.x).arg(point.y)
        }).join("; ")
    }

    function conditionText(series) {
        const conditions = []
        if (series.frequencyHz !== undefined && series.frequencyHz !== null) {
            conditions.push(qsTr("frequency %1 Hz").arg(series.frequencyHz))
        }
        if (series.temperatureC !== undefined && series.temperatureC !== null) {
            conditions.push(qsTr("temperature %1 °C").arg(series.temperatureC))
        }
        if (series.dcBiasAPerM !== undefined && series.dcBiasAPerM !== null) {
            conditions.push(qsTr("DC bias %1 A/m").arg(series.dcBiasAPerM))
        }
        return conditions.length > 0
            ? conditions.join(" · ")
            : qsTr("conditions unspecified")
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
        const padding = high === low ? Math.max(Math.abs(low) * 0.1, 1) : (high - low) * 0.08
        return [low - padding, high + padding]
    }

    function plotX(value, range) {
        return plotLeft + (value - range[0]) / (range[1] - range[0])
            * Math.max(1, curveCanvas.width - plotLeft - plotRight)
    }

    function plotY(value, range) {
        return curveCanvas.height - plotBottom
            - (value - range[0]) / (range[1] - range[0])
            * Math.max(1, curveCanvas.height - plotTop - plotBottom)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 6

        Label {
            id: curvePlotTitle
            objectName: "curvePlotTitle"
            Layout.fillWidth: true
            text: qsTr("Curve preview")
            font.bold: true
        }

        Label {
            id: curvePlotDetails
            objectName: "curvePlotDetails"
            Layout.fillWidth: true
            text: materialCurveEditor.activeSeries.seriesId
                ? qsTr("%1 · %2 · %3 · source: %4")
                    .arg(materialCurveEditor.activeSeries.seriesId)
                    .arg(materialCurveEditor.activeSeries.kind === "bh-curve"
                        ? qsTr("B-H curve") : qsTr("Loss table"))
                    .arg(materialCurveEditor.conditionText(materialCurveEditor.activeSeries))
                    .arg(materialCurveEditor.activeSeries.sourceFilename
                        || materialCurveEditor.activeSeries.sourceKind
                        || qsTr("table"))
                : qsTr("Select a material revision and series to inspect its curve.")
            wrapMode: Text.WordWrap
            color: palette.mid
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: 22
            Label {
                id: curvePlotYAxisLabel
                objectName: "curvePlotYAxisLabel"
                anchors.centerIn: parent
                rotation: -90
                text: materialCurveEditor.activeSeries.yUnit
                    ? qsTr("Y: %1").arg(materialCurveEditor.activeSeries.yUnit)
                    : qsTr("Y value")
            }
        }

        Canvas {
            id: curveCanvas
            objectName: "materialCurveCanvas"
            Layout.fillWidth: true
            Layout.preferredHeight: 220
            Accessible.name: qsTr("Current material curve plot")
            onPaint: {
                const context = getContext("2d")
                context.reset()
                const left = materialCurveEditor.plotLeft
                const right = width - materialCurveEditor.plotRight
                const top = materialCurveEditor.plotTop
                const bottom = height - materialCurveEditor.plotBottom
                context.strokeStyle = palette.mid
                context.lineWidth = 1
                context.strokeRect(left, top, Math.max(1, right - left), Math.max(1, bottom - top))
                context.strokeStyle = palette.mid
                context.globalAlpha = 0.28
                for (let step = 1; step < 4; ++step) {
                    const x = left + (right - left) * step / 4
                    const y = top + (bottom - top) * step / 4
                    context.beginPath()
                    context.moveTo(x, top)
                    context.lineTo(x, bottom)
                    context.moveTo(left, y)
                    context.lineTo(right, y)
                    context.stroke()
                }
                context.globalAlpha = 1
                if (materialCurveEditor.pointModel.length === 0) {
                    return
                }
                const xRange = materialCurveEditor.valueRange("x")
                const yRange = materialCurveEditor.valueRange("y")
                context.strokeStyle = palette.highlight
                context.fillStyle = palette.highlight
                context.lineWidth = 2
                context.beginPath()
                for (let index = 0; index < materialCurveEditor.pointModel.length; ++index) {
                    const point = materialCurveEditor.pointModel[index]
                    const x = materialCurveEditor.plotX(point.x, xRange)
                    const y = materialCurveEditor.plotY(point.y, yRange)
                    if (index === 0) {
                        context.moveTo(x, y)
                    } else {
                        context.lineTo(x, y)
                    }
                }
                context.stroke()
                for (let index = 0; index < materialCurveEditor.pointModel.length; ++index) {
                    const point = materialCurveEditor.pointModel[index]
                    context.beginPath()
                    context.arc(
                        materialCurveEditor.plotX(point.x, xRange),
                        materialCurveEditor.plotY(point.y, yRange),
                        4, 0, Math.PI * 2
                    )
                    context.fill()
                }
            }

            Connections {
                target: materialCurveEditor.controller
                function onSelectionChanged() { curveCanvas.requestPaint() }
                function onEditorReset() {
                    materialCurveEditor.pendingCanonicalPoints = ({})
                    curveCanvas.requestPaint()
                }
            }
        }

        Label {
            id: curvePlotXAxisLabel
            objectName: "curvePlotXAxisLabel"
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: materialCurveEditor.activeSeries.xUnit
                ? qsTr("X: %1").arg(materialCurveEditor.activeSeries.xUnit)
                : qsTr("X value")
        }

        Label {
            id: curvePlotEmptyState
            objectName: "curvePlotEmptyState"
            Layout.fillWidth: true
            visible: materialCurveEditor.pointModel.length === 0
            text: qsTr(
                "No curve points are available. Import a CSV or XLSX material table, then select a revision."
            )
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            color: palette.mid
            Accessible.name: text
        }

        Label {
            objectName: "importedPointComparison"
            Layout.fillWidth: true
            text: materialCurveEditor.controller !== null
                    && materialCurveEditor.controller.sourceComparisonAvailable
                ? qsTr("Imported points: %1").arg(
                    materialCurveEditor.pointText(materialCurveEditor.importedPointModel)
                )
                : qsTr("Imported points: no baseline comparison is available")
            wrapMode: Text.WordWrap
            Accessible.name: text
        }
        Label {
            objectName: "currentPointComparison"
            Layout.fillWidth: true
            text: qsTr("Current canonical points: %1").arg(
                materialCurveEditor.pointText(materialCurveEditor.pointModel)
            )
            wrapMode: Text.WordWrap
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
