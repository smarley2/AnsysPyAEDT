import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: simulationPanel
    objectName: "simulationPanel"
    property var controller: null
    property var generation: null

    // ponytail: JS String() drops the trailing ".0" that Python's str(float)
    // keeps (String(1.0) === "1"), so a plain String() cast here would show
    // "1" for a percent error the project actually stores as 1.0. Restore the
    // ".0" for integral values so the field reflects what is on disk.
    function floatText(value) {
        return Number.isInteger(value) ? value.toFixed(1) : String(value)
    }

    function refreshFields() {
        if (controller === null) {
            return
        }
        passesField.text = String(controller.maximumPasses)
        percentErrorField.text = simulationPanel.floatText(controller.percentError)
        backendCombo.currentIndex = Math.max(0, controller.backendOptions.indexOf(controller.backend))
        meshCombo.currentIndex = Math.max(0, controller.meshIntentOptions.indexOf(controller.meshIntent))
    }

    Connections {
        target: simulationPanel.controller
        function onConfigurationChanged() { simulationPanel.refreshFields() }
    }

    Component.onCompleted: refreshFields()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: simulationPanel.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Simulation")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Configure a run")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Frequency and temperature belong to the shared operating point on the Windings screen and are not repeated here.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            Label { text: qsTr("Backend") }
            ComboBox {
                id: backendCombo
                objectName: "simulationBackendCombo"
                Layout.fillWidth: true
                activeFocusOnTab: true
                model: simulationPanel.controller !== null ? simulationPanel.controller.backendOptions : []
                Accessible.name: qsTr("Solver backend")
                onActivated: simulationPanel.controller.setBackend(currentText)
            }

            Label {
                objectName: "simulationModeLabel"
                Layout.fillWidth: true
                text: simulationPanel.controller === null
                    ? ""
                    : qsTr("Run mode: %1 — %2")
                        .arg(simulationPanel.controller.modeLabel)
                        .arg(simulationPanel.controller.modeNote)
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
                Accessible.name: text
            }

            Label { text: qsTr("Mesh intent") }
            ComboBox {
                id: meshCombo
                objectName: "simulationMeshIntentCombo"
                Layout.fillWidth: true
                activeFocusOnTab: true
                model: simulationPanel.controller !== null ? simulationPanel.controller.meshIntentOptions : []
                Accessible.name: qsTr("Mesh intent")
                onActivated: simulationPanel.controller.setMeshIntent(currentText)
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Maximum passes") }
                TextField {
                    id: passesField
                    objectName: "simulationMaximumPassesField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: IntValidator { bottom: 1; top: 1000 }
                    Accessible.name: qsTr("Maximum adaptive passes")
                    onEditingFinished: {
                        if (!simulationPanel.controller.setMaximumPasses(text)) {
                            simulationPanel.refreshFields()
                        }
                    }
                }
                Label { text: qsTr("Percent error") }
                TextField {
                    id: percentErrorField
                    objectName: "simulationPercentErrorField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Convergence percent error")
                    onEditingFinished: {
                        if (!simulationPanel.controller.setPercentError(text)) {
                            simulationPanel.refreshFields()
                        }
                    }
                }
            }

            Label { text: qsTr("Requested outputs"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: requestedOutputs
                objectName: "simulationRequestedOutputs"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(32, count * 32)
                interactive: false
                model: simulationPanel.controller !== null ? simulationPanel.controller.requestedOutputs : []
                Accessible.name: qsTr("Requested solver outputs")

                delegate: CheckBox {
                    required property var modelData
                    width: ListView.view.width
                    height: 32
                    activeFocusOnTab: true
                    text: modelData.label
                    checked: modelData.selected
                    Accessible.name: qsTr("Request %1").arg(modelData.label)
                    onToggled: simulationPanel.controller.toggleRequestedOutput(modelData.value, checked)
                }
            }

            CheckBox {
                id: showSolverWindowCheckBox
                objectName: "showSolverWindowCheckBox"
                Layout.fillWidth: true
                activeFocusOnTab: true
                text: qsTr("Show solver window")
                enabled: simulationPanel.controller !== null
                    && simulationPanel.controller.visibleWindowSupported
                checked: simulationPanel.controller !== null
                    && simulationPanel.controller.showSolverWindow
                Accessible.name: qsTr("Show the solver window for this run")
                onToggled: {
                    if (!simulationPanel.controller.setShowSolverWindow(checked)) {
                        checked = simulationPanel.controller.showSolverWindow
                    }
                }
            }

            Label {
                objectName: "showSolverWindowReason"
                Layout.fillWidth: true
                visible: text !== ""
                text: simulationPanel.controller === null
                    ? ""
                    : simulationPanel.controller.visibleWindowReason
                wrapMode: Text.WordWrap
                color: "#a45528"
                Accessible.name: text
            }

            Button {
                objectName: "simulationGenerateButton"
                Layout.fillWidth: true
                activeFocusOnTab: true
                text: simulationPanel.generation !== null && simulationPanel.generation.busy
                    ? qsTr("Generating…") : qsTr("Generate project")
                enabled: simulationPanel.controller !== null && simulationPanel.controller.canGenerate
                Accessible.name: qsTr("Generate the solver project")
                onClicked: simulationPanel.controller.generate()
            }

            Label {
                objectName: "simulationBlockedReason"
                Layout.fillWidth: true
                visible: text !== ""
                text: simulationPanel.controller === null ? "" : simulationPanel.controller.blockedReason
                wrapMode: Text.WordWrap
                color: "#a45528"
                Accessible.name: text
            }

            ListView {
                objectName: "simulationRunLog"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(180, Math.max(0, count * 22))
                clip: true
                model: simulationPanel.generation !== null ? simulationPanel.generation.lines : []
                Accessible.name: qsTr("Generation log")
                delegate: Label {
                    required property string modelData
                    width: ListView.view.width
                    text: modelData
                    elide: Text.ElideRight
                    font.pixelSize: 11
                    color: "#1e2b32"
                }
            }
        }
    }
}
