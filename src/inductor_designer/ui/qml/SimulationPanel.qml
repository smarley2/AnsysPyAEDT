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
        id: simulationScrollView
        objectName: "simulationScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        // Reserve the vertical scrollbar's own fixed width unconditionally
        // instead of binding to `availableWidth`: `availableWidth` reserves
        // for the scrollbar based on content height, which here depends on
        // this column's own width (wrapping `Label`s) -- see
        // `WindingPanel.qml` for the feedback-loop staleness this avoids.
        property real scrollBarReserve: ScrollBar.vertical ? ScrollBar.vertical.width : 0

        ColumnLayout {
            width: simulationScrollView.width - simulationScrollView.leftPadding
                - simulationScrollView.scrollBarReserve
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("Design / Simulation")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Configure a run")
                font.pixelSize: 24
                font.bold: true
                wrapMode: Text.WordWrap
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

            Label { text: qsTr("Run mode") }
            ComboBox {
                id: modeCombo
                objectName: "simulationModeCombo"
                Layout.fillWidth: true
                activeFocusOnTab: true
                model: simulationPanel.controller !== null ? simulationPanel.controller.modeOptions : []
                Accessible.name: qsTr("Run mode")
                onActivated: simulationPanel.controller.setMode(currentText)
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

            // `width: parent.width`, not `Layout.fillWidth: true`: matches
            // `WindingPanel.qml`'s nested `GridLayout`s -- an ordinary
            // property binding tracks the `ColumnLayout`'s width reliably
            // even after it shrinks, where `Layout.fillWidth`'s internal
            // re-arrange was observed not to (see `WindingPanel.qml` for the
            // feedback-loop staleness this avoids). Both labels also get
            // `Layout.fillWidth: true` / `Layout.minimumWidth: 0` /
            // `wrapMode: Text.WordWrap`, the same idiom `WindingPanel.qml`
            // uses for every label beside a shrinkable field, so a longer
            // label added here later shares the row with its field instead
            // of claiming it outright.
            GridLayout {
                width: parent.width
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Maximum passes") }
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
                Label { Layout.fillWidth: true; Layout.minimumWidth: 0; wrapMode: Text.WordWrap; text: qsTr("Percent error") }
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
                onClicked: {
                    // generate() itself records the pending AC-only
                    // confirmation when it refuses (SimulationController),
                    // so it must always be called first -- opening the
                    // dialog without it would leave proceedAcOnly() with
                    // nothing to confirm.
                    if (simulationPanel.controller.generate()) {
                        return
                    }
                    if (simulationPanel.controller.dcBiasIgnored) {
                        dcBiasConfirmDialog.open()
                    }
                }
            }

            Button {
                objectName: "simulationCancelButton"
                Layout.fillWidth: true
                activeFocusOnTab: true
                text: qsTr("Cancel run")
                // A run stops at its next stage boundary, never mid-call, so
                // this stays enabled for as long as the run is in flight.
                enabled: simulationPanel.generation !== null && simulationPanel.generation.busy
                Accessible.name: qsTr("Cancel the running solver job")
                onClicked: simulationPanel.controller.cancel()
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
                // Size to the *actual* wrapped content (contentHeight), not
                // an assumed 22px-per-line heuristic that undercounts any
                // entry which wraps to more than one line -- capped so a
                // hundred log lines cannot push the rest of the layout
                // apart. Past the cap the view stays interactive (its
                // default), so the remainder is reachable by scrolling
                // rather than silently clipped.
                Layout.preferredHeight: Math.min(180, Math.max(0, contentHeight))
                clip: true
                model: simulationPanel.generation !== null ? simulationPanel.generation.lines : []
                Accessible.name: qsTr("Generation log")
                delegate: Label {
                    required property string modelData
                    width: ListView.view.width
                    text: modelData
                    wrapMode: Text.WordWrap
                    font.pixelSize: 11
                    color: "#1e2b32"
                }
            }
        }
    }

    // The selected backend (Maxwell 2D or FEMM) linearizes about zero bias
    // and cannot carry a DC premagnetization into an AC solve (decision:
    // Fabio Posser, 2026-08-07). A sibling of the ScrollView, not a Layout
    // child, matching the `unsavedProjectDialog` / `dirtyMaterialTransactionDialog`
    // convention. Generate() itself refuses to start until Proceed is
    // clicked, so Cancel truly starts nothing.
    Dialog {
        id: dcBiasConfirmDialog
        objectName: "dcBiasConfirmDialog"
        anchors.centerIn: parent
        modal: true
        closePolicy: Popup.NoAutoClose
        title: qsTr("DC bias will be ignored")

        ColumnLayout {
            Label {
                objectName: "dcBiasConfirmMessage"
                Layout.preferredWidth: 420
                text: simulationPanel.controller === null
                    ? "" : simulationPanel.controller.dcBiasNotice
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button {
                    objectName: "dcBiasConfirmProceedButton"
                    text: qsTr("Proceed AC-only")
                    activeFocusOnTab: true
                    Accessible.name: qsTr(
                        "Proceed with an AC-only run and ignore the DC bias"
                    )
                    onClicked: {
                        dcBiasConfirmDialog.close()
                        simulationPanel.controller.proceedAcOnly()
                    }
                }
                Button {
                    objectName: "dcBiasConfirmCancelButton"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Cancel; do not start the run")
                    onClicked: dcBiasConfirmDialog.close()
                }
            }
        }
    }
}
