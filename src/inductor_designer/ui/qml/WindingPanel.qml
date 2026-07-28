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

    function refreshFields() {
        const item = currentWinding()
        turnsField.text = item.turns === undefined ? "" : String(item.turns)
        conductorField.text = item.conductor === undefined ? "" : String(item.conductor)
        currentField.text = item.acRmsCurrentA === undefined ? "" : String(item.acRmsCurrentA)
        phaseField.text = item.acPhaseDeg === undefined ? "" : String(item.acPhaseDeg)
        startAngleField.text = item.startAngleDeg === undefined ? "" : String(item.startAngleDeg)
        sectorField.text = item.sectorDeg === undefined ? "" : String(item.sectorDeg)
        spacingField.text = item.spacingMm === undefined ? "" : String(item.spacingMm)
        directionField.currentIndex = item.direction === "ccw" ? 1 : 0
        windingList.currentIndex = Math.max(0, controller === null
            ? -1
            : controller.windings.findIndex(function(row) {
                return row.windingId === controller.selectedWindingId
            }))
    }

    function applyField(field, editor) {
        if (controller !== null
                && !controller.setWindingField(controller.selectedWindingId, field, editor.text)) {
            refreshFields()
        }
    }

    Connections {
        target: windingsPanel.controller
        function onWindingsChanged() { windingsPanel.refreshFields() }
        function onSelectedWindingIdChanged() { windingsPanel.refreshFields() }
    }

    Component.onCompleted: refreshFields()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: windingsPanel.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Windings")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Define windings")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Set the operating point and placement. The canvas updates from validated geometry.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            ListView {
                id: windingList
                objectName: "windingList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(160, Math.max(52, count * 52))
                clip: true
                spacing: 6
                currentIndex: 0
                model: windingsPanel.controller !== null
                    ? windingsPanel.controller.windings : []
                Accessible.name: qsTr("Winding list")

                delegate: ItemDelegate {
                    required property var modelData
                    required property int index
                    width: ListView.view.width
                    height: 46
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

            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: "#d8d4cd"
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

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Turns") }
                TextField {
                    id: turnsField
                    objectName: "windingTurnsField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("turns", turnsField)
                }
                Label { text: qsTr("Conductor") }
                TextField {
                    id: conductorField
                    objectName: "windingConductorField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("conductor", conductorField)
                }
                Label { text: qsTr("AC RMS current") }
                TextField {
                    id: currentField
                    objectName: "windingCurrentField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("acRmsCurrentA", currentField)
                }
                Label { text: qsTr("AC phase") }
                TextField {
                    id: phaseField
                    objectName: "windingPhaseField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("acPhaseDeg", phaseField)
                }
                Label { text: qsTr("Start angle") }
                TextField {
                    id: startAngleField
                    objectName: "windingStartAngleField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("startAngleDeg", startAngleField)
                }
                Label { text: qsTr("Sector") }
                TextField {
                    id: sectorField
                    objectName: "windingSectorField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("sectorDeg", sectorField)
                }
                Label { text: qsTr("Spacing") }
                TextField {
                    id: spacingField
                    objectName: "windingSpacingField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    onEditingFinished: windingsPanel.applyField("spacingMm", spacingField)
                }
                Label { text: qsTr("Direction") }
                ComboBox {
                    id: directionField
                    objectName: "windingDirectionField"
                    Layout.fillWidth: true
                    model: [qsTr("cw"), qsTr("ccw")]
                    onActivated: {
                        if (windingsPanel.controller !== null
                                && !windingsPanel.controller.setWindingField(
                                    windingsPanel.controller.selectedWindingId,
                                    "direction",
                                    currentText
                                )) {
                            windingsPanel.refreshFields()
                        }
                    }
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
                    text: qsTr("Clearance is checked against the real core and conductor geometry before an edit is accepted.")
                    wrapMode: Text.WordWrap
                    color: "#a45528"
                }
            }
        }
    }
}
