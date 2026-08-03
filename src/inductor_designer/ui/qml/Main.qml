import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import QtQuick.Window

ApplicationWindow {
    id: window
    objectName: "canvasFirstShell"
    property bool wideStep: guidedStepList.currentIndex === 2
        || guidedStepList.currentIndex === 4
    property bool allowCloseOnce: false
    width: Math.min(1800, Math.max(1200, Math.round(Screen.width * 0.82)))
    height: Math.min(1100, Math.max(760, Math.round(Screen.height * 0.84)))
    minimumWidth: 1000
    minimumHeight: 700
    visible: true
    color: "#f3f1ed"
    title: qsTr("PyAEDT Inductor Designer")

    function requestStep(index) {
        guidedStepList.currentIndex = index
    }

    function stepEyebrow() {
        switch (guidedStepList.currentIndex) {
        case 0: return qsTr("Design / Core & Material")
        case 1: return qsTr("Design / Windings")
        case 2: return qsTr("Design / Preliminary")
        case 3: return qsTr("Design / Simulation")
        default: return qsTr("Design / Review")
        }
    }

    function stepTitle() {
        switch (guidedStepList.currentIndex) {
        case 0: return qsTr("Pair a core and material")
        case 1: return qsTr("Define windings")
        case 2: return qsTr("Preliminary estimates")
        case 3: return qsTr("Configure a run")
        default: return qsTr("Review before generation")
        }
    }

    // Exposed as a testable function rather than inlined in `onClosing`
    // because Qt has no supported way to reach a window's `onClosing` handler
    // from a test -- `requestApplicationClose()` is what the handler
    // delegates to, and what the tests call directly.
    function requestApplicationClose() {
        if (allowCloseOnce) {
            // Save/Discard on the unsaved-project dialog re-issue window.close()
            // once the blocking condition is gone, which re-enters this
            // function; without this bypass that second call would just see
            // the (still momentarily dirty, or freshly re-evaluated) state
            // again and loop back into a dialog instead of actually closing.
            allowCloseOnce = false
            return true
        }
        if (materialStudioController !== null && materialStudioController.dirty) {
            // Never lose a material draft to an application close: surface the
            // window that owns the unsaved edit and let its dialog decide.
            // This guard takes precedence over the project session below.
            materialStudioWindow.show()
            materialStudioWindow.requestClose()
            return false
        }
        if (guidedStudioController !== null && guidedStudioController.dirty) {
            // Never lose unsaved winding, core, material-pin, or simulation
            // edits held by the project session either.
            unsavedProjectDialog.open()
            return false
        }
        return true
    }

    onClosing: function(close) {
        close.accepted = window.requestApplicationClose()
    }

    ObjectModel {
        id: guidedStepsModel

        ItemDelegate {
            id: coreMaterialStep
            objectName: "coreMaterialStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Core & Material")
            highlighted: guidedStepList.currentIndex === 0
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(0)
            Keys.onReturnPressed: window.requestStep(0)
            Keys.onEnterPressed: window.requestStep(0)
            Keys.onSpacePressed: window.requestStep(0)
            background: Rectangle {
                radius: 8
                color: coreMaterialStep.highlighted ? "#e9efff" : "transparent"
                border.color: coreMaterialStep.highlighted ? "#2e65e7" : "transparent"
            }
        }
        ItemDelegate {
            id: windingsStep
            objectName: "windingsStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Windings")
            highlighted: guidedStepList.currentIndex === 1
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(1)
            Keys.onReturnPressed: window.requestStep(1)
            Keys.onEnterPressed: window.requestStep(1)
            Keys.onSpacePressed: window.requestStep(1)
            background: Rectangle {
                radius: 8
                color: windingsStep.highlighted ? "#e9efff" : "transparent"
                border.color: windingsStep.highlighted ? "#2e65e7" : "transparent"
            }
        }
        ItemDelegate {
            id: preliminaryStep
            objectName: "preliminaryStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Preliminary")
            highlighted: guidedStepList.currentIndex === 2
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(2)
            Keys.onReturnPressed: window.requestStep(2)
            Keys.onEnterPressed: window.requestStep(2)
            Keys.onSpacePressed: window.requestStep(2)
            background: Rectangle {
                radius: 8
                color: preliminaryStep.highlighted ? "#e9efff" : "transparent"
                border.color: preliminaryStep.highlighted ? "#2e65e7" : "transparent"
            }
        }
        ItemDelegate {
            id: simulationStep
            objectName: "simulationStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Simulation")
            highlighted: guidedStepList.currentIndex === 3
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(3)
            Keys.onReturnPressed: window.requestStep(3)
            Keys.onEnterPressed: window.requestStep(3)
            Keys.onSpacePressed: window.requestStep(3)
            background: Rectangle {
                radius: 8
                color: simulationStep.highlighted ? "#e9efff" : "transparent"
                border.color: simulationStep.highlighted ? "#2e65e7" : "transparent"
            }
        }
        ItemDelegate {
            id: reviewStep
            objectName: "reviewStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Review")
            highlighted: guidedStepList.currentIndex === 4
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(4)
            Keys.onReturnPressed: window.requestStep(4)
            Keys.onEnterPressed: window.requestStep(4)
            Keys.onSpacePressed: window.requestStep(4)
            background: Rectangle {
                radius: 8
                color: reviewStep.highlighted ? "#e9efff" : "transparent"
                border.color: reviewStep.highlighted ? "#2e65e7" : "transparent"
            }
        }
    }

    ColumnLayout {
        id: shellLayout
        objectName: "shellLayout"
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        Rectangle {
            id: topbar
            objectName: "topbar"
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            color: "#fbfaf8"
            radius: 10
            border.color: "#d8d4cd"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 12
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 36
                    radius: 10
                    color: "#1e2b32"
                    Label {
                        anchors.centerIn: parent
                        text: qsTr("ID")
                        color: "#ffffff"
                        font.bold: true
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Label {
                        text: qsTr("PyAEDT Inductor Designer")
                        font.pixelSize: 15
                        font.bold: true
                        color: "#1e2b32"
                    }
                    Label {
                        text: qsTr("Guided Studio · %1").arg(window.stepTitle())
                        color: "#6d7a7e"
                        font.pixelSize: 12
                    }
                }
                Label {
                    objectName: "saveStateLabel"
                    text: guidedStudioController === null
                        ? qsTr("No project loaded")
                        : (guidedStudioController.dirty ? qsTr("Unsaved changes") : qsTr("Saved"))
                    color: guidedStudioController !== null && guidedStudioController.dirty
                        ? "#a45528" : "#157a61"
                }
                Button {
                    objectName: "saveProjectButton"
                    text: qsTr("Save")
                    enabled: guidedStudioController !== null
                        && guidedStudioController.dirty
                    onClicked: guidedStudioController.saveDraft()
                }
            }
        }

        Rectangle {
            id: stepRail
            objectName: "stepRail"
            Layout.fillWidth: true
            Layout.preferredHeight: 74
            color: "#fbfaf8"
            radius: 10
            border.color: "#d8d4cd"

            ListView {
                id: guidedStepList
                objectName: "guidedStepList"
                anchors.fill: parent
                anchors.margins: 5
                orientation: ListView.Horizontal
                activeFocusOnTab: true
                clip: true
                currentIndex: guidedStudioController !== null ? 1 : 0
                model: guidedStepsModel
                Accessible.name: qsTr("Guided Studio steps")

                Keys.onRightPressed: function(event) {
                    window.requestStep(Math.min(currentIndex + 1, count - 1))
                    event.accepted = true
                }
                Keys.onLeftPressed: function(event) {
                    window.requestStep(Math.max(currentIndex - 1, 0))
                    event.accepted = true
                }
            }
        }

        RowLayout {
            id: workspace
            objectName: "workspace"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 10

            Rectangle {
                id: canvasCard
                objectName: "canvasCard"
                visible: !window.wideStep
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#fbfaf8"
                radius: 10
                border.color: "#d8d4cd"

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 10

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("%1").arg(window.stepEyebrow())
                            color: "#6d7a7e"
                            font.pixelSize: 11
                            font.letterSpacing: 1.1
                        }
                        Item { Layout.fillWidth: true }
                        Button { text: qsTr("Fit") }
                        Button { text: qsTr("3D"); highlighted: true }
                        Button { text: qsTr("Section"); enabled: false; ToolTip.text: qsTr("Section preview follows the geometry slice.") }
                    }

                    Label {
                        Layout.fillWidth: true
                        text: qsTr("Live geometry preview")
                        font.pixelSize: 24
                        font.bold: true
                        color: "#1e2b32"
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true

                        PreviewPane {
                            anchors.fill: parent
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.margins: 12
                            width: 170
                            height: 30
                            radius: 6
                            color: "#ffffffcc"
                            border.color: "#d8d4cd"
                            Label {
                                anchors.centerIn: parent
                                text: qsTr("mm · real geometry")
                                color: "#6d7a7e"
                                font.pixelSize: 11
                            }
                        }
                    }
                }
            }

            Rectangle {
                id: contextPanel
                objectName: "contextPanel"
                Layout.fillWidth: window.wideStep
                Layout.preferredWidth: window.wideStep
                    ? window.width
                    : Math.max(330, Math.min(410, window.width * 0.29))
                Layout.minimumWidth: 300
                Layout.fillHeight: true
                color: "#fbfaf8"
                radius: 10
                border.color: "#d8d4cd"

                StackLayout {
                    anchors.fill: parent
                    anchors.margins: 4
                    currentIndex: guidedStepList.currentIndex

                    CoreMaterialPanel {
                        // Deviation from the task brief: the brief's Main.qml
                        // snippet sets objectName: "coreMaterialPanelHost"
                        // here, but QML instance-site property assignments
                        // override a component's own root-level assignment
                        // (verified empirically), so that would shadow
                        // CoreMaterialPanel.qml's own
                        // `objectName: "coreMaterialPanel"` and break
                        // test_core_material_panel_exposes_both_selectors_and_manual_dimensions,
                        // which requires "coreMaterialPanel" to resolve via
                        // findChild. No test references
                        // "coreMaterialPanelHost", so the override is simply
                        // omitted.
                        controller: coreMaterialController
                    }

                    WindingPanel {
                        controller: guidedStudioController
                    }

                    PreliminaryPage {
                        controller: preliminaryController
                    }

                    SimulationPanel {
                        controller: simulationController
                        generation: generationController
                    }

                    ReviewPage {
                        controller: reviewController
                    }
                }
            }
        }

        Rectangle {
            id: statusDock
            objectName: "statusDock"
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: "#fbfaf8"
            radius: 10
            border.color: "#d8d4cd"

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 10
                spacing: 10
                Label {
                    text: guidedStudioController !== null
                        ? guidedStudioController.statusMessage : qsTr("Preview only")
                    color: "#157a61"
                    Layout.minimumWidth: 100
                }
                Label {
                    text: qsTr("Geometry source: domain model")
                    color: "#6d7a7e"
                    font.pixelSize: 11
                }
                Item { Layout.fillWidth: true }
                Label {
                    visible: generationController !== null && generationController.lines.length > 0
                    text: visible ? generationController.lines[generationController.lines.length - 1] : ""
                    elide: Text.ElideRight
                    Layout.maximumWidth: 300
                }
                Label {
                    text: qsTr("Ready")
                    color: "#6d7a7e"
                }
            }
        }
    }

    MaterialStudioWindow {
        id: materialStudioWindow
        controller: materialStudioController
        onClosedAfterEditing: {
            if (coreMaterialController !== null) {
                coreMaterialController.refreshLibrary()
            }
        }
    }

    Connections {
        target: coreMaterialController
        function onMaterialStudioRequested() {
            materialStudioWindow.show()
            materialStudioWindow.raise()
            materialStudioWindow.requestActivate()
        }
    }

    Dialog {
        id: unsavedProjectDialog
        objectName: "unsavedProjectDialog"
        anchors.centerIn: parent
        modal: true
        closePolicy: Popup.NoAutoClose
        title: qsTr("Unsaved project changes")

        ColumnLayout {
            Label {
                Layout.preferredWidth: 420
                text: qsTr(
                    "Save the project, discard unsaved changes, or cancel closing."
                )
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button {
                    objectName: "unsavedProjectSaveButton"
                    text: qsTr("Save")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Save the project and close")
                    onClicked: {
                        if (guidedStudioController.saveDraft()) {
                            unsavedProjectDialog.close()
                            window.allowCloseOnce = true
                            window.close()
                        }
                        // A failed save leaves the dialog and the window open:
                        // the failure is already reported in the status bar.
                    }
                }
                Button {
                    objectName: "unsavedProjectDiscardButton"
                    text: qsTr("Discard")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Discard unsaved changes and close")
                    onClicked: {
                        unsavedProjectDialog.close()
                        window.allowCloseOnce = true
                        window.close()
                    }
                }
                Button {
                    objectName: "unsavedProjectCancelButton"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Cancel closing and keep editing")
                    onClicked: unsavedProjectDialog.close()
                }
            }
        }
    }
}
