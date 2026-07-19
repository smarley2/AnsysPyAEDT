import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQml.Models

ApplicationWindow {
    id: window
    width: 1200
    height: 760
    visible: true
    title: qsTr("PyAEDT Inductor Designer")

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
            onClicked: guidedStepList.currentIndex = 0
            Keys.onReturnPressed: guidedStepList.currentIndex = 0
            Keys.onEnterPressed: guidedStepList.currentIndex = 0
            Keys.onSpacePressed: guidedStepList.currentIndex = 0
        }
        ItemDelegate {
            objectName: "windingsStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Windings")
            highlighted: guidedStepList.currentIndex === 1
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: guidedStepList.currentIndex = 1
            Keys.onReturnPressed: guidedStepList.currentIndex = 1
            Keys.onEnterPressed: guidedStepList.currentIndex = 1
            Keys.onSpacePressed: guidedStepList.currentIndex = 1
        }
        ItemDelegate {
            objectName: "materialsStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Materials")
            highlighted: guidedStepList.currentIndex === 2
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: guidedStepList.currentIndex = 2
            Keys.onReturnPressed: guidedStepList.currentIndex = 2
            Keys.onEnterPressed: guidedStepList.currentIndex = 2
            Keys.onSpacePressed: guidedStepList.currentIndex = 2
        }
        ItemDelegate {
            objectName: "simulationStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Simulation")
            highlighted: guidedStepList.currentIndex === 3
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: guidedStepList.currentIndex = 3
            Keys.onReturnPressed: guidedStepList.currentIndex = 3
            Keys.onEnterPressed: guidedStepList.currentIndex = 3
            Keys.onSpacePressed: guidedStepList.currentIndex = 3
        }
        ItemDelegate {
            objectName: "reviewStep"
            width: guidedStepList.width
            height: 44
            text: qsTr("Review")
            highlighted: guidedStepList.currentIndex === 4
            activeFocusOnTab: true
            Accessible.name: text
            onClicked: guidedStepList.currentIndex = 4
            Keys.onReturnPressed: guidedStepList.currentIndex = 4
            Keys.onEnterPressed: guidedStepList.currentIndex = 4
            Keys.onSpacePressed: guidedStepList.currentIndex = 4
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
                        currentIndex = Math.min(currentIndex + 1, count - 1)
                        event.accepted = true
                    }
                    Keys.onUpPressed: function(event) {
                        currentIndex = Math.max(currentIndex - 1, 0)
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
}
