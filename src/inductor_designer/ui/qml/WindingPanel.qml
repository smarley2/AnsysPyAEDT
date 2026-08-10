import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: windingsPanel
    objectName: "windingsPanel"
    property var controller: null

    function currentWinding() {
        if (controller === null) {
            return ({})
        }
        for (let index = 0; index < controller.windings.length; ++index) {
            if (controller.windings[index].windingId === controller.selectedWindingId) {
                return controller.windings[index]
            }
        }
        return controller.windings.length > 0 ? controller.windings[0] : ({})
    }

    function textOf(value) {
        return value === undefined || value === null ? "" : String(value)
    }

    // Python's str(float) always keeps a decimal point ("25.0"); JS's
    // String(Number) drops it for whole values ("25"). The winding row and
    // operating-point dicts marshal Python floats into plain JS numbers with
    // no type tag, so a whole-valued field (e.g. a 25 C temperature) would
    // otherwise render as "25" and mismatch anything comparing against the
    // domain's own str() formatting. Turns is the only integer-typed field
    // and stays on textOf().
    function numberText(value) {
        if (value === undefined || value === null) {
            return ""
        }
        return Number.isInteger(value) ? value.toFixed(1) : String(value)
    }

    function indexIn(values, value) {
        const position = values.indexOf(value)
        return position < 0 ? 0 : position
    }

    function refreshFields() {
        const item = currentWinding()
        const point = controller === null ? ({}) : controller.operatingPoint
        frequencyField.text = numberText(point.frequencyHz)
        windingTemperatureField.text = numberText(point.windingTemperatureC)
        coreTemperatureField.text = numberText(point.coreTemperatureC)
        turnsField.text = textOf(item.turns)
        labelField.text = textOf(item.label)
        currentField.text = numberText(item.acRmsCurrentA)
        phaseField.text = numberText(item.acPhaseDeg)
        dcCurrentField.text = numberText(item.dcCurrentA)
        startAngleField.text = numberText(item.startAngleDeg)
        sectorField.text = numberText(item.sectorDeg)
        spacingField.text = numberText(item.spacingMm)
        clearanceField.text = numberText(item.clearanceMm)
        terminalIntentField.text = textOf(item.terminalIntent)
        if (controller !== null) {
            conductorCombo.currentIndex = indexIn(controller.conductorNames, item.conductor)
            modeCombo.currentIndex = indexIn(controller.conductorModes, item.mode)
            currentDirectionCombo.currentIndex = indexIn(
                controller.currentDirections, item.currentDirection)
            directionField.currentIndex = indexIn(controller.windingDirections, item.direction)
            windingList.currentIndex = Math.max(0, controller.windings.findIndex(function(row) {
                return row.windingId === controller.selectedWindingId
            }))
        }
    }

    function applyField(field, editor) {
        if (controller !== null
                && !controller.setWindingField(controller.selectedWindingId, field, editor.text)) {
            refreshFields()
        }
    }

    function applyChoice(field, value) {
        if (controller !== null
                && !controller.setWindingField(controller.selectedWindingId, field, value)) {
            refreshFields()
        }
    }

    function applyOperatingPoint(field, editor) {
        if (controller !== null && !controller.setOperatingPointField(field, editor.text)) {
            refreshFields()
        }
    }

    Connections {
        target: windingsPanel.controller
        function onWindingsChanged() { windingsPanel.refreshFields() }
        function onSelectedWindingIdChanged() { windingsPanel.refreshFields() }
        function onOperatingPointChanged() { windingsPanel.refreshFields() }
    }

    Component.onCompleted: refreshFields()

    ScrollView {
        id: windingsScrollView
        objectName: "windingsScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        // `availableWidth` reserves room for the vertical scrollbar
        // dynamically, based on content height -- but content height here
        // depends on this column's own width (wrapping `Label`s), so
        // binding the column's width to `availableWidth` closes a feedback
        // loop: Qt Quick Layouts was observed to leave a nested
        // `GridLayout`'s `Layout.fillWidth` children stuck at a stale width
        // once that loop settled (reproduced at width=1000, height=300 on
        // this screen). Reserving the scrollbar's own fixed, style-defined
        // width unconditionally instead breaks the loop; the only cost is a
        // few unused pixels on the right when no scrollbar is needed.
        property real scrollBarReserve: ScrollBar.vertical ? ScrollBar.vertical.width : 0

        ColumnLayout {
            width: windingsScrollView.width - windingsScrollView.leftPadding
                - windingsScrollView.scrollBarReserve
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("Design / Windings")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Define windings")
                font.pixelSize: 24
                font.bold: true
                wrapMode: Text.WordWrap
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("One frequency and two temperatures are shared by every winding. Editors block invalid characters; the domain still validates the committed value.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            Label { text: qsTr("Shared operating point"); font.bold: true; color: "#1e2b32" }

            // `width: parent.width`, not `Layout.fillWidth: true`: this is
            // the nested `GridLayout` the class comment above refers to --
            // an ordinary property binding tracks `ColumnLayout`'s width
            // reliably even after it shrinks, where `Layout.fillWidth`'s
            // internal re-arrange was observed not to.
            GridLayout {
                width: parent.width
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Frequency (Hz)") }
                TextField {
                    id: frequencyField
                    objectName: "operatingFrequencyField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0 }
                    Accessible.name: qsTr("Shared frequency in hertz")
                    onEditingFinished: windingsPanel.applyOperatingPoint("frequencyHz", frequencyField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Winding temperature (°C)") }
                TextField {
                    id: windingTemperatureField
                    objectName: "windingTemperatureField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Winding temperature in degrees Celsius")
                    onEditingFinished: windingsPanel.applyOperatingPoint(
                        "windingTemperatureC", windingTemperatureField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Core temperature (°C)") }
                TextField {
                    id: coreTemperatureField
                    objectName: "coreTemperatureField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Core temperature in degrees Celsius")
                    onEditingFinished: windingsPanel.applyOperatingPoint(
                        "coreTemperatureC", coreTemperatureField)
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#d8d4cd" }

            ListView {
                id: windingList
                objectName: "windingList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(160, Math.max(52, count * 52))
                clip: true
                spacing: 6
                currentIndex: 0
                model: windingsPanel.controller !== null ? windingsPanel.controller.windings : []
                Accessible.name: qsTr("Winding list")

                delegate: ItemDelegate {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    height: 46
                    activeFocusOnTab: true
                    highlighted: ListView.isCurrentItem
                    text: qsTr("%1  ·  %2 turns  ·  %3")
                        .arg(modelData.windingId)
                        .arg(modelData.turns)
                        .arg(modelData.conductor)
                    Accessible.name: qsTr("Select winding %1").arg(modelData.windingId)
                    onClicked: {
                        windingList.currentIndex = index
                        windingsPanel.controller.selectWinding(modelData.windingId)
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    id: addWindingButton
                    objectName: "addWindingButton"
                    Layout.fillWidth: true
                    text: qsTr("Add winding")
                    activeFocusOnTab: true
                    enabled: windingsPanel.controller !== null
                    Accessible.name: text
                    onClicked: windingsPanel.controller.addWinding()
                }
                Button {
                    id: removeWindingButton
                    objectName: "removeWindingButton"
                    Layout.fillWidth: true
                    text: qsTr("Remove winding")
                    activeFocusOnTab: true
                    enabled: windingsPanel.controller !== null
                        && windingsPanel.controller.windings.length > 1
                    Accessible.name: qsTr("Remove the selected winding")
                    onClicked: windingsPanel.controller.removeWinding(
                        windingsPanel.controller.selectedWindingId)
                }
            }

            Label {
                Layout.fillWidth: true
                text: {
                    const item = windingsPanel.currentWinding()
                    return item.windingId === undefined
                        ? qsTr("No winding selected")
                        : qsTr("Selected · %1").arg(item.label)
                }
                font.bold: true
                color: "#1e2b32"
            }

            // `width: parent.width`, not `Layout.fillWidth: true`: this is
            // the nested `GridLayout` the class comment above refers to --
            // an ordinary property binding tracks `ColumnLayout`'s width
            // reliably even after it shrinks, where `Layout.fillWidth`'s
            // internal re-arrange was observed not to.
            GridLayout {
                width: parent.width
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Label") }
                TextField {
                    id: labelField
                    objectName: "windingLabelField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Winding label")
                    onEditingFinished: windingsPanel.applyField("label", labelField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Turns") }
                TextField {
                    id: turnsField
                    objectName: "windingTurnsField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: 100000 }
                    Accessible.name: qsTr("Turn count, integers only")
                    onEditingFinished: windingsPanel.applyField("turns", turnsField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Conductor") }
                ComboBox {
                    id: conductorCombo
                    objectName: "windingConductorCombo"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.conductorNames : []
                    Accessible.name: qsTr("Conductor")
                    onActivated: windingsPanel.applyChoice("conductor", currentText)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Conductor mode") }
                ComboBox {
                    id: modeCombo
                    objectName: "windingModeCombo"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.conductorModes : []
                    Accessible.name: qsTr("Conductor mode")
                    onActivated: windingsPanel.applyChoice("mode", currentText)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("AC RMS current (A)") }
                TextField {
                    id: currentField
                    objectName: "windingCurrentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("AC RMS current in amperes")
                    onEditingFinished: windingsPanel.applyField("acRmsCurrentA", currentField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("AC phase (deg)") }
                TextField {
                    id: phaseField
                    objectName: "windingPhaseField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: -360.0; top: 360.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("AC phase in degrees")
                    onEditingFinished: windingsPanel.applyField("acPhaseDeg", phaseField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("DC current (A)") }
                TextField {
                    id: dcCurrentField
                    objectName: "windingDcCurrentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("DC current in amperes")
                    onEditingFinished: windingsPanel.applyField("dcCurrentA", dcCurrentField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Current direction") }
                ComboBox {
                    id: currentDirectionCombo
                    objectName: "windingCurrentDirectionCombo"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.currentDirections : []
                    Accessible.name: qsTr("Current direction")
                    onActivated: windingsPanel.applyChoice("currentDirection", currentText)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Start angle (deg)") }
                TextField {
                    id: startAngleField
                    objectName: "windingStartAngleField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; top: 359.999; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Start angle in degrees")
                    onEditingFinished: windingsPanel.applyField("startAngleDeg", startAngleField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Sector (deg)") }
                TextField {
                    id: sectorField
                    objectName: "windingSectorField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; top: 360.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Sector span in degrees")
                    onEditingFinished: windingsPanel.applyField("sectorDeg", sectorField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Spacing (mm)") }
                TextField {
                    id: spacingField
                    objectName: "windingSpacingField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Minimum turn spacing in millimetres")
                    onEditingFinished: windingsPanel.applyField("spacingMm", spacingField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Clearance (mm)") }
                TextField {
                    id: clearanceField
                    objectName: "windingClearanceField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Minimum clearance in millimetres")
                    onEditingFinished: windingsPanel.applyField("clearanceMm", clearanceField)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Winding direction") }
                ComboBox {
                    id: directionField
                    objectName: "windingDirectionField"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    model: windingsPanel.controller !== null
                        ? windingsPanel.controller.windingDirections : []
                    Accessible.name: qsTr("Winding direction")
                    onActivated: windingsPanel.applyChoice("direction", currentText)
                }
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Terminal intent") }
                TextField {
                    id: terminalIntentField
                    objectName: "windingTerminalIntentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Terminal intent, free text")
                    onEditingFinished: windingsPanel.applyField("terminalIntent", terminalIntentField)
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#fff4ec"
                radius: 6
                implicitHeight: clearanceText.implicitHeight + 20

                Label {
                    id: clearanceText
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: qsTr("Clearance and spacing are checked against the real core and conductor geometry before an edit is accepted.")
                    wrapMode: Text.WordWrap
                    color: "#a45528"
                    Accessible.name: text
                }
            }
        }
    }
}
