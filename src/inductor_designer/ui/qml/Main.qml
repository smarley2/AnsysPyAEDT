import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import QtQuick.Window

ApplicationWindow {
    id: window
    objectName: "canvasFirstShell"
    property string pendingMaterialAction: ""
    property var pendingMaterialArguments: []
    property bool allowCloseOnce: false
    width: Math.min(1800, Math.max(1200, Math.round(Screen.width * 0.82)))
    height: Math.min(1100, Math.max(760, Math.round(Screen.height * 0.84)))
    minimumWidth: 1000
    minimumHeight: 700
    visible: true
    color: "#f3f1ed"
    title: qsTr("PyAEDT Inductor Designer")

    function requestStep(index) {
        if (index === guidedStepList.currentIndex) {
            return
        }
        requestMaterialAction("navigate", [index])
    }

    function requestMaterialAction(action, arguments_) {
        if (materialStudioController !== null
                && materialStudioController.dirty) {
            pendingMaterialAction = action
            pendingMaterialArguments = arguments_
            dirtyMaterialTransactionDialog.open()
            return
        }
        executeMaterialAction(action, arguments_)
    }

    function executeMaterialAction(action, arguments_) {
        if (action === "navigate") {
            guidedStepList.currentIndex = arguments_[0]
        } else if (action === "closeApplication") {
            allowCloseOnce = true
            window.close()
        } else {
            materialStudioPage.performTransactionAction(action, arguments_)
        }
    }

    function completePendingMaterialAction() {
        const action = pendingMaterialAction
        const arguments_ = pendingMaterialArguments
        pendingMaterialAction = ""
        pendingMaterialArguments = []
        dirtyMaterialTransactionDialog.close()
        executeMaterialAction(action, arguments_)
    }

    function stepEyebrow() {
        switch (guidedStepList.currentIndex) {
        case 0: return qsTr("Design / Core")
        case 1: return qsTr("Design / Windings")
        case 2: return qsTr("Design / Materials")
        case 3: return qsTr("Design / Simulation")
        default: return qsTr("Design / Review")
        }
    }

    function stepTitle() {
        switch (guidedStepList.currentIndex) {
        case 0: return qsTr("Choose a core")
        case 1: return qsTr("Define windings")
        case 2: return qsTr("Pin materials")
        case 3: return qsTr("Configure a run")
        default: return qsTr("Review before generation")
        }
    }

    onClosing: function(close) {
        if (allowCloseOnce) {
            allowCloseOnce = false
            close.accepted = true
        } else if (materialStudioController !== null
                && materialStudioController.dirty) {
            close.accepted = false
            requestMaterialAction("closeApplication", [])
        }
    }

    ObjectModel {
        id: guidedStepsModel

        ItemDelegate {
            id: coreStep
            objectName: "coreStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Core")
            highlighted: guidedStepList.currentIndex === 0
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(0)
            Keys.onReturnPressed: window.requestStep(0)
            Keys.onEnterPressed: window.requestStep(0)
            Keys.onSpacePressed: window.requestStep(0)
            background: Rectangle {
                radius: 8
                color: coreStep.highlighted ? "#e9efff" : "transparent"
                border.color: coreStep.highlighted ? "#2e65e7" : "transparent"
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
            id: materialsStep
            objectName: "materialsStep"
            width: Math.max(140, guidedStepList.width / 5)
            height: 64
            text: qsTr("Materials")
            highlighted: guidedStepList.currentIndex === 2
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(2)
            Keys.onReturnPressed: window.requestStep(2)
            Keys.onEnterPressed: window.requestStep(2)
            Keys.onSpacePressed: window.requestStep(2)
            background: Rectangle {
                radius: 8
                color: materialsStep.highlighted ? "#e9efff" : "transparent"
                border.color: materialsStep.highlighted ? "#2e65e7" : "transparent"
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
                Layout.preferredWidth: Math.max(330, Math.min(410, window.width * 0.29))
                Layout.minimumWidth: 300
                Layout.fillHeight: true
                color: "#fbfaf8"
                radius: 10
                border.color: "#d8d4cd"

                StackLayout {
                    anchors.fill: parent
                    anchors.margins: 4
                    currentIndex: guidedStepList.currentIndex

                    ScrollView {
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width - 20
                            anchors.margins: 10
                            spacing: 12
                            Label { text: qsTr("Design / Core"); color: "#6d7a7e" }
                            Label { text: qsTr("Choose a core"); font.pixelSize: 24; font.bold: true; color: "#1e2b32" }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("Select a traceable catalog record or define a manual toroid before placing windings.")
                                wrapMode: Text.WordWrap
                                color: "#6d7a7e"
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                height: 120
                                radius: 8
                                color: "#f3f1ed"
                                Label {
                                    anchors.centerIn: parent
                                    text: qsTr("Core selection workspace")
                                    color: "#6d7a7e"
                                }
                            }
                        }
                    }

                    WindingPanel {
                        controller: guidedStudioController
                    }

                    MaterialStudioPage {
                        id: materialStudioPage
                        objectName: "materialStudioPage"
                        controller: materialStudioController
                        transactionHost: window
                    }

                    ScrollView {
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width - 20
                            anchors.margins: 10
                            spacing: 12
                            Label { text: qsTr("Design / Simulation"); color: "#6d7a7e" }
                            Label { text: qsTr("Configure a run"); font.pixelSize: 24; font.bold: true; color: "#1e2b32" }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("Choose a backend and requested outputs. Generation remains behind the existing controller.")
                                wrapMode: Text.WordWrap
                                color: "#6d7a7e"
                            }
                            ComboBox {
                                objectName: "simulationBackendCombo"
                                Layout.fillWidth: true
                                model: backendChoices
                                enabled: generationController !== null
                            }
                            Button {
                                objectName: "simulationGenerateButton"
                                Layout.fillWidth: true
                                text: generationController !== null && generationController.busy
                                    ? qsTr("Generating…") : qsTr("Generate project")
                                enabled: generationController !== null && !generationController.busy
                                onClicked: generationController.generate(simulationBackendCombo.currentText)
                            }
                        }
                    }

                    ScrollView {
                        clip: true
                        contentWidth: availableWidth
                        ColumnLayout {
                            width: parent.width - 20
                            anchors.margins: 10
                            spacing: 12
                            Label { text: qsTr("Design / Review"); color: "#6d7a7e" }
                            Label { text: qsTr("Review before generation"); font.pixelSize: 24; font.bold: true; color: "#1e2b32" }
                            Label {
                                Layout.fillWidth: true
                                text: qsTr("Check the selected core, windings, materials, and solver intent before a project is generated.")
                                wrapMode: Text.WordWrap
                                color: "#6d7a7e"
                            }
                            Label { text: qsTr("✓ Geometry inputs available"); color: "#157a61" }
                            Label { text: qsTr("✓ Material selection available"); color: "#157a61" }
                            Label { text: qsTr("○ Solver outputs pending"); color: "#6d7a7e" }
                        }
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

    Dialog {
        id: dirtyMaterialTransactionDialog
        objectName: "dirtyMaterialTransactionDialog"
        anchors.centerIn: parent
        modal: true
        closePolicy: Popup.NoAutoClose
        title: qsTr("Unsaved material changes")

        ColumnLayout {
            Label {
                Layout.preferredWidth: 420
                text: qsTr(
                    "Save the material draft, discard unsaved changes, or cancel the pending action."
                )
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button {
                    objectName: "dirtyMaterialTransactionSaveButton"
                    text: qsTr("Save")
                    enabled: materialStudioController !== null
                        && materialStudioController.canSave
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Save material changes and continue")
                    onClicked: {
                        materialStudioController.saveDraft()
                        if (!materialStudioController.dirty) {
                            window.completePendingMaterialAction()
                        }
                    }
                }
                Button {
                    objectName: "dirtyMaterialTransactionDiscardButton"
                    text: qsTr("Discard")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Discard material changes and continue")
                    onClicked: {
                        if (materialStudioController.discardChanges()) {
                            window.completePendingMaterialAction()
                        }
                    }
                }
                Button {
                    objectName: "dirtyMaterialTransactionCancelButton"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Cancel action and keep editing")
                    onClicked: {
                        window.pendingMaterialAction = ""
                        window.pendingMaterialArguments = []
                        dirtyMaterialTransactionDialog.close()
                    }
                }
            }
        }
    }
}
