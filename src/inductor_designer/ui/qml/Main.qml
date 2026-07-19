import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models

ApplicationWindow {
    id: window
    property int pendingStepIndex: -1
    width: 1200
    height: 760
    visible: true
    title: qsTr("PyAEDT Inductor Designer")

    function requestStep(index) {
        if (index === guidedStepList.currentIndex) {
            return
        }
        if (guidedStepList.currentIndex === 2
                && materialStudioController !== null
                && materialStudioController.dirty) {
            pendingStepIndex = index
            dirtyNavigationDialog.open()
            return
        }
        guidedStepList.currentIndex = index
    }

    function completePendingNavigation() {
        if (pendingStepIndex >= 0) {
            guidedStepList.currentIndex = pendingStepIndex
        }
        pendingStepIndex = -1
        dirtyNavigationDialog.close()
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
            Layout.preferredWidth: 320
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
                    objectName: "materialStudioPage"
                    controller: materialStudioController
                }
                Item { objectName: "simulationPage" }
                Item { objectName: "reviewPage" }
            }
        }
    }

    Dialog {
        id: dirtyNavigationDialog
        objectName: "dirtyNavigationDialog"
        anchors.centerIn: parent
        modal: true
        closePolicy: Popup.NoAutoClose
        title: qsTr("Unsaved material changes")

        ColumnLayout {
            Label {
                Layout.preferredWidth: 420
                text: qsTr(
                    "Save the material draft, discard unsaved changes, or cancel navigation."
                )
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Button {
                    objectName: "dirtyNavigationSaveButton"
                    text: qsTr("Save")
                    enabled: materialStudioController !== null
                        && materialStudioController.canSave
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Save material changes and leave")
                    onClicked: {
                        materialStudioController.saveDraft()
                        if (!materialStudioController.dirty) {
                            window.completePendingNavigation()
                        }
                    }
                }
                Button {
                    objectName: "dirtyNavigationDiscardButton"
                    text: qsTr("Discard")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Discard material changes and leave")
                    onClicked: {
                        if (materialStudioController.discardChanges()) {
                            window.completePendingNavigation()
                        }
                    }
                }
                Button {
                    objectName: "dirtyNavigationCancelButton"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Cancel navigation and keep editing")
                    onClicked: {
                        window.pendingStepIndex = -1
                        dirtyNavigationDialog.close()
                    }
                }
            }
        }
    }
}
