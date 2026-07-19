import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models
import QtQuick.Window

ApplicationWindow {
    id: window
    property string pendingMaterialAction: ""
    property var pendingMaterialArguments: []
    property bool allowCloseOnce: false
    width: Math.min(1800, Math.max(1200, Math.round(Screen.width * 0.78)))
    height: Math.min(1100, Math.max(760, Math.round(Screen.height * 0.82)))
    minimumWidth: 1000
    minimumHeight: 700
    visible: true
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
            objectName: "coreStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Core")
            highlighted: guidedStepList.currentIndex === 0
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(0)
            Keys.onReturnPressed: window.requestStep(0)
            Keys.onEnterPressed: window.requestStep(0)
            Keys.onSpacePressed: window.requestStep(0)
        }
        ItemDelegate {
            objectName: "windingsStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Windings")
            highlighted: guidedStepList.currentIndex === 1
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(1)
            Keys.onReturnPressed: window.requestStep(1)
            Keys.onEnterPressed: window.requestStep(1)
            Keys.onSpacePressed: window.requestStep(1)
        }
        ItemDelegate {
            objectName: "materialsStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Materials")
            highlighted: guidedStepList.currentIndex === 2
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(2)
            Keys.onReturnPressed: window.requestStep(2)
            Keys.onEnterPressed: window.requestStep(2)
            Keys.onSpacePressed: window.requestStep(2)
        }
        ItemDelegate {
            objectName: "simulationStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Simulation")
            highlighted: guidedStepList.currentIndex === 3
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(3)
            Keys.onReturnPressed: window.requestStep(3)
            Keys.onEnterPressed: window.requestStep(3)
            Keys.onSpacePressed: window.requestStep(3)
        }
        ItemDelegate {
            objectName: "reviewStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Review")
            highlighted: guidedStepList.currentIndex === 4
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: window.requestStep(4)
            Keys.onReturnPressed: window.requestStep(4)
            Keys.onEnterPressed: window.requestStep(4)
            Keys.onSpacePressed: window.requestStep(4)
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Frame {
            Layout.preferredWidth: Math.max(230, Math.min(340, Math.round(window.width * 0.22)))
            Layout.minimumWidth: 230
            Layout.maximumWidth: 340
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent

                ListView {
                    id: guidedStepList
                    objectName: "guidedStepList"
                    Layout.fillWidth: true
                    Layout.preferredHeight: count * 44
                    activeFocusOnTab: true
                    clip: true
                    currentIndex: 0
                    model: guidedStepsModel
                    Accessible.name: qsTr("Guided Studio steps")

                    Keys.onDownPressed: function(event) {
                        window.requestStep(Math.min(currentIndex + 1, count - 1))
                        event.accepted = true
                    }
                    Keys.onUpPressed: function(event) {
                        window.requestStep(Math.max(currentIndex - 1, 0))
                        event.accepted = true
                    }
                }

                Column {
                    Layout.fillWidth: true
                    Repeater {
                        model: simulationSummary
                        delegate: Text {
                            required property string modelData
                            text: modelData
                            wrapMode: Text.WordWrap
                            font.pixelSize: 12
                        }
                    }
                }

                ColumnLayout {
                    visible: generationController !== null
                    Layout.fillWidth: true
                    ComboBox {
                        id: backendCombo
                        Layout.fillWidth: true
                        model: backendChoices
                        activeFocusOnTab: true
                        Accessible.name: qsTr("Generation backend")
                    }
                    Button {
                        text: generationController !== null && generationController.busy
                            ? qsTr("Generating…")
                            : qsTr("Generate")
                        enabled: generationController !== null && !generationController.busy
                        activeFocusOnTab: true
                        Accessible.name: text
                        onClicked: generationController.generate(backendCombo.currentText)
                    }
                    Column {
                        Layout.fillWidth: true
                        Repeater {
                            model: generationController !== null ? generationController.lines : []
                            delegate: Text {
                                required property string modelData
                                text: modelData
                                wrapMode: Text.WordWrap
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }
                Label { text: qsTr("Foundation preview spike") }
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            PreviewPane {
                objectName: "previewPane"
                anchors.fill: parent
                visible: guidedStepList.currentIndex !== 2
            }

            StackLayout {
                anchors.fill: parent
                currentIndex: guidedStepList.currentIndex

                Item { objectName: "corePage" }
                Item { objectName: "windingsPage" }
                MaterialStudioPage {
                    id: materialStudioPage
                    objectName: "materialStudioPage"
                    controller: materialStudioController
                    transactionHost: window
                }
                Item { objectName: "simulationPage" }
                Item { objectName: "reviewPage" }
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
