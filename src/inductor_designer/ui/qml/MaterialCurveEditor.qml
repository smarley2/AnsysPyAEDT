import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialCurveEditor
    objectName: "materialCurveEditor"
    property var controller: null
    property var pointModel: controller !== null ? controller.points : []
    property bool logX: false
    property bool logY: false
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
    property var visiblePointModel: filteredPoints()
    property var xRange: axisRange("x", logX)
    property var yRange: axisRange("y", logY)
    property var xTickModel: axisTicks(xRange, logX)
    property var yTickModel: axisTicks(yRange, logY).reverse()
    property real plotLeft: 60
    property real plotRight: 14
    property real plotTop: 12
    property real plotBottom: 40

    onLogXChanged: curveCanvas.requestPaint()
    onLogYChanged: curveCanvas.requestPaint()
    onPointModelChanged: curveCanvas.requestPaint()

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
        return conditions.length > 0 ? conditions.join(" · ") : qsTr("conditions unspecified")
    }

    function filteredPoints() {
        return pointModel.filter(function(point) {
            return (!logX || point.x > 0) && (!logY || point.y > 0)
        })
    }

    function transformed(value, logarithmic) {
        return logarithmic ? Math.log(value) / Math.LN10 : value
    }

    function axisRange(axis, logarithmic) {
        const values = visiblePointModel
            .map(function(point) { return transformed(point[axis], logarithmic) })
            .filter(function(value) { return Number.isFinite(value) })
        if (values.length === 0) {
            return logarithmic ? [0, 1] : [0, 1]
        }
        let low = values[0]
        let high = low
        for (let index = 1; index < values.length; ++index) {
            low = Math.min(low, values[index])
            high = Math.max(high, values[index])
        }
        if (low === high) {
            const padding = Math.max(Math.abs(low) * 0.1, 1)
            return [low - padding, high + padding]
        }
        return [low, high]
    }

    function axisTicks(range, logarithmic) {
        const ticks = []
        for (let index = 0; index < 5; ++index) {
            const transformedValue = range[0] + (range[1] - range[0]) * index / 4
            ticks.push(logarithmic ? Math.pow(10, transformedValue) : transformedValue)
        }
        return ticks
    }

    function formatValue(value) {
        if (!Number.isFinite(value)) {
            return ""
        }
        return Number(value).toPrecision(4).replace(/\.0+$/, "")
    }

    function plotCoordinate(value, range, logarithmic) {
        const transformedValue = transformed(value, logarithmic)
        return (transformedValue - range[0]) / (range[1] - range[0])
    }

    function plotX(value) {
        return plotLeft + plotCoordinate(value, xRange, logX)
            * Math.max(1, curveCanvas.width - plotLeft - plotRight)
    }

    function plotY(value) {
        return curveCanvas.height - plotBottom
            - plotCoordinate(value, yRange, logY)
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

        ComboBox {
            id: curveSeriesChoice
            objectName: "curveSeriesChoice"
            Layout.fillWidth: true
            model: materialCurveEditor.controller !== null
                ? materialCurveEditor.controller.series : []
            textRole: "seriesId"
            valueRole: "seriesId"
            currentIndex: {
                const currentId = materialCurveEditor.activeSeries.seriesId
                for (let index = 0; index < count; ++index) {
                    if (model[index].seriesId === currentId) {
                        return index
                    }
                }
                return count > 0 ? 0 : -1
            }
            onActivated: materialCurveEditor.controller.selectSeries(currentValue)
            Accessible.name: qsTr("Read-only material series")
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
                    .arg(materialCurveEditor.activeSeries.sourceFilename || qsTr("table"))
                : qsTr("Select a material revision and series to inspect its curve.")
            wrapMode: Text.WordWrap
            color: palette.mid
        }

        RowLayout {
            Layout.fillWidth: true
            CheckBox {
                id: logXCheckBox
                objectName: "logXCheckBox"
                text: qsTr("Log X")
                checked: materialCurveEditor.logX
                onToggled: materialCurveEditor.logX = checked
                onCheckedChanged: {
                    if (materialCurveEditor.logX !== checked) {
                        materialCurveEditor.logX = checked
                    }
                }
            }
            CheckBox {
                id: logYCheckBox
                objectName: "logYCheckBox"
                text: qsTr("Log Y")
                checked: materialCurveEditor.logY
                onToggled: materialCurveEditor.logY = checked
                onCheckedChanged: {
                    if (materialCurveEditor.logY !== checked) {
                        materialCurveEditor.logY = checked
                    }
                }
            }
            Item { Layout.fillWidth: true }
        }

        Label {
            id: curvePlotLogNotice
            objectName: "curvePlotLogNotice"
            Layout.fillWidth: true
            visible: (materialCurveEditor.logX || materialCurveEditor.logY)
                && materialCurveEditor.visiblePointModel.length < materialCurveEditor.pointModel.length
            text: qsTr("Logarithmic preview omits non-positive points on the selected axis; stored data is unchanged.")
            wrapMode: Text.WordWrap
            color: palette.mid
            Accessible.name: text
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 4

            ColumnLayout {
                id: curvePlotYAxisTicks
                objectName: "curvePlotYAxisTicks"
                Layout.preferredWidth: 54
                Layout.fillHeight: true
                Repeater {
                    model: materialCurveEditor.yTickModel
                    delegate: Label {
                        required property var modelData
                        required property int index
                        objectName: "curvePlotYAxisTick-" + index
                        Layout.fillHeight: true
                        Layout.alignment: Qt.AlignRight
                        text: materialCurveEditor.formatValue(modelData)
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }

            Canvas {
                id: curveCanvas
                objectName: "materialCurveCanvas"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 230
                Accessible.name: qsTr("Read-only material curve plot")

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
                    const points = materialCurveEditor.visiblePointModel
                    if (points.length === 0) {
                        return
                    }
                    context.strokeStyle = palette.highlight
                    context.fillStyle = palette.highlight
                    context.lineWidth = 2
                    context.beginPath()
                    for (let index = 0; index < points.length; ++index) {
                        const point = points[index]
                        const x = materialCurveEditor.plotX(point.x)
                        const y = materialCurveEditor.plotY(point.y)
                        if (index === 0) {
                            context.moveTo(x, y)
                        } else {
                            context.lineTo(x, y)
                        }
                    }
                    context.stroke()
                    for (let index = 0; index < points.length; ++index) {
                        const point = points[index]
                        context.beginPath()
                        context.arc(materialCurveEditor.plotX(point.x), materialCurveEditor.plotY(point.y), 4, 0, Math.PI * 2)
                        context.fill()
                    }
                }

                Connections {
                    target: materialCurveEditor.controller
                    function onSelectionChanged() { curveCanvas.requestPaint() }
                    function onEditorReset() { curveCanvas.requestPaint() }
                }
            }
        }

        Label {
            id: curvePlotYAxisLabel
            objectName: "curvePlotYAxisLabel"
            Layout.fillWidth: true
            text: materialCurveEditor.activeSeries.yUnit
                ? qsTr("Y: %1").arg(materialCurveEditor.activeSeries.yUnit)
                : qsTr("Y value")
        }

        RowLayout {
            id: curvePlotXAxisTicks
            objectName: "curvePlotXAxisTicks"
            Layout.fillWidth: true
            Layout.leftMargin: 58
            Layout.rightMargin: 12
            Repeater {
                model: materialCurveEditor.xTickModel
                delegate: Label {
                    required property var modelData
                    required property int index
                    objectName: "curvePlotXAxisTick-" + index
                    Layout.fillWidth: true
                    horizontalAlignment: index === 0
                        ? Text.AlignLeft : index === 4 ? Text.AlignRight : Text.AlignHCenter
                    text: materialCurveEditor.formatValue(modelData)
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
            text: qsTr("No curve points are available. Import a CSV or XLSX material table, then select a revision.")
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            color: palette.mid
            Accessible.name: text
        }
    }
}
