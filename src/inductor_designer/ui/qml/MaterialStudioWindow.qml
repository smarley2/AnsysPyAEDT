import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: materialStudioWindow
    objectName: "materialStudioWindow"
    property var controller: null
    property string pendingMaterialAction: ""
    property var pendingMaterialArguments: []
    property bool allowCloseOnce: false
    signal closedAfterEditing()

    width: Math.min(1600, Math.max(1100, Math.round(Screen.width * 0.72)))
    height: Math.min(1000, Math.max(700, Math.round(Screen.height * 0.78)))
    minimumWidth: 900
    minimumHeight: 640
    visible: false
    color: "#f3f1ed"
    title: qsTr("Material Studio")

    function requestMaterialAction(action, arguments_) {
        if (controller !== null && controller.dirty) {
            pendingMaterialAction = action
            pendingMaterialArguments = arguments_
            dirtyMaterialTransactionDialog.open()
            return
        }
        executeMaterialAction(action, arguments_)
    }

    function executeMaterialAction(action, arguments_) {
        if (action === "closeWindow") {
            allowCloseOnce = true
            materialStudioWindow.close()
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

    function requestClose() {
        requestMaterialAction("closeWindow", [])
    }

    onClosing: function(close) {
        if (allowCloseOnce) {
            allowCloseOnce = false
            close.accepted = true
            materialStudioWindow.closedAfterEditing()
        } else if (controller !== null && controller.dirty) {
            close.accepted = false
            requestMaterialAction("closeWindow", [])
        } else {
            close.accepted = true
            materialStudioWindow.closedAfterEditing()
        }
    }

    Item {
        id: materialStudioHost
        anchors.fill: parent
        anchors.margins: 8

        // Deviation from the task brief: the brief's snippet anchors
        // MaterialStudioPage directly (anchors.fill: parent). Verified
        // empirically that both anchors.fill and Layout.fillWidth/fillHeight
        // keep re-imposing width from this window's geometry on every
        // subsequent processEvents() once the (previously hidden) window is
        // shown, permanently defeating the explicit width override that
        // test_material_page_reflows_for_compact_and_wide_windows relies on
        // (materialOverviewGrid stayed at 2 columns instead of 1). A plain
        // property binding, by contrast, is replaced outright the moment the
        // test assigns page.width explicitly -- matching the sizing
        // behaviour the page had as a StackLayout child before this task,
        // where an explicit width override stuck for the rest of the test.
        MaterialStudioPage {
            id: materialStudioPage
            objectName: "materialStudioPage"
            width: materialStudioHost.width
            height: materialStudioHost.height
            controller: materialStudioWindow.controller
            transactionHost: materialStudioWindow
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
                    enabled: materialStudioWindow.controller !== null
                        && materialStudioWindow.controller.canSave
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Save material changes and continue")
                    onClicked: {
                        materialStudioWindow.controller.saveDraft()
                        if (!materialStudioWindow.controller.dirty) {
                            materialStudioWindow.completePendingMaterialAction()
                        }
                    }
                }
                Button {
                    objectName: "dirtyMaterialTransactionDiscardButton"
                    text: qsTr("Discard")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Discard material changes and continue")
                    onClicked: {
                        if (materialStudioWindow.controller.discardChanges()) {
                            materialStudioWindow.completePendingMaterialAction()
                        }
                    }
                }
                Button {
                    objectName: "dirtyMaterialTransactionCancelButton"
                    text: qsTr("Cancel")
                    activeFocusOnTab: true
                    Accessible.name: qsTr("Cancel action and keep editing")
                    onClicked: {
                        materialStudioWindow.pendingMaterialAction = ""
                        materialStudioWindow.pendingMaterialArguments = []
                        dirtyMaterialTransactionDialog.close()
                    }
                }
            }
        }
    }
}
