import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: coreMaterialPanel
    objectName: "coreMaterialPanel"
    property var controller: null

    function selectedManualCore() {
        return controller !== null && controller.selectedCore.kind === "manual"
            ? controller.selectedCore : ({})
    }

    function refreshManualFields() {
        const core = selectedManualCore()
        outerField.text = core.outerDiameterMm === undefined ? "" : String(core.outerDiameterMm)
        innerField.text = core.innerDiameterMm === undefined ? "" : String(core.innerDiameterMm)
        heightField.text = core.heightMm === undefined ? "" : String(core.heightMm)
        cornerField.text = core.cornerRadiusMm === undefined ? "" : String(core.cornerRadiusMm)
    }

    Connections {
        target: coreMaterialPanel.controller
        function onSelectionChanged() { coreMaterialPanel.refreshManualFields() }
    }

    Component.onCompleted: refreshManualFields()

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: coreMaterialPanel.width - 24
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("Design / Core & Material")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Pair a core with an exact material revision")
                font.pixelSize: 24
                font.bold: true
                wrapMode: Text.WordWrap
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Each selection filters the other list. An incompatible pairing is cleared and explained; nothing is substituted for you.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            Label { text: qsTr("Catalog cores"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: coreOptionList
                objectName: "coreOptionList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(180, Math.max(52, count * 52))
                clip: true
                spacing: 6
                model: coreMaterialPanel.controller !== null
                    ? coreMaterialPanel.controller.coreOptions : []
                Accessible.name: qsTr("Catalog core list")

                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width
                    height: 46
                    activeFocusOnTab: true
                    highlighted: coreMaterialPanel.controller !== null
                        && coreMaterialPanel.controller.selectedCore.partNumber === modelData.partNumber
                    text: qsTr("%1  ·  %2  ·  %3")
                        .arg(modelData.partNumber)
                        .arg(modelData.manufacturer)
                        .arg(modelData.materialLabel)
                    Accessible.name: qsTr("Select core %1").arg(modelData.partNumber)
                    onClicked: coreMaterialPanel.controller.selectCatalogCore(modelData.partNumber)
                    Keys.onReturnPressed: coreMaterialPanel.controller.selectCatalogCore(modelData.partNumber)
                }
            }

            Label { text: qsTr("Manual core"); font.bold: true; color: "#1e2b32" }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 10
                rowSpacing: 8

                Label { text: qsTr("Outer diameter (mm)") }
                TextField {
                    id: outerField
                    objectName: "manualCoreOuterField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core outer diameter in millimetres")
                }
                Label { text: qsTr("Inner diameter (mm)") }
                TextField {
                    id: innerField
                    objectName: "manualCoreInnerField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core inner diameter in millimetres")
                }
                Label { text: qsTr("Height (mm)") }
                TextField {
                    id: heightField
                    objectName: "manualCoreHeightField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core height in millimetres")
                }
                Label { text: qsTr("Corner radius (mm)") }
                TextField {
                    id: cornerField
                    objectName: "manualCoreCornerField"
                    Layout.fillWidth: true
                    selectByMouse: true
                    activeFocusOnTab: true
                    inputMethodHints: Qt.ImhFormattedNumbersOnly
                    validator: DoubleValidator { bottom: 0.0; notation: DoubleValidator.StandardNotation }
                    Accessible.name: qsTr("Manual core corner radius in millimetres")
                }
            }

            Button {
                id: applyManualCoreButton
                objectName: "applyManualCoreButton"
                Layout.fillWidth: true
                text: qsTr("Use these manual dimensions")
                activeFocusOnTab: true
                enabled: coreMaterialPanel.controller !== null
                    && outerField.acceptableInput && innerField.acceptableInput
                    && heightField.acceptableInput && cornerField.acceptableInput
                    && outerField.text !== "" && innerField.text !== "" && heightField.text !== ""
                Accessible.name: text
                onClicked: coreMaterialPanel.controller.applyManualCore(
                    Number(outerField.text),
                    Number(innerField.text),
                    Number(heightField.text),
                    cornerField.text === "" ? 0.0 : Number(cornerField.text))
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: "#d8d4cd" }

            Label { text: qsTr("Material revisions"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: materialOptionList
                objectName: "materialOptionList"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(180, Math.max(52, count * 52))
                clip: true
                spacing: 6
                model: coreMaterialPanel.controller !== null
                    ? coreMaterialPanel.controller.materialOptions : []
                Accessible.name: qsTr("Material revision list")

                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width
                    height: 46
                    activeFocusOnTab: true
                    highlighted: coreMaterialPanel.controller !== null
                        && coreMaterialPanel.controller.selectedMaterial.revisionId === modelData.revisionId
                    text: qsTr("%1 %2 %3  ·  %4  ·  %5")
                        .arg(modelData.manufacturer)
                        .arg(modelData.name)
                        .arg(modelData.grade)
                        .arg(modelData.revisionId)
                        .arg(modelData.status)
                    Accessible.name: qsTr("Select material revision %1").arg(modelData.revisionId)
                    onClicked: coreMaterialPanel.controller.selectMaterial(
                        modelData.manufacturer,
                        modelData.name,
                        modelData.grade,
                        modelData.revisionId,
                        modelData.bhSeriesIds.length === 1 ? modelData.bhSeriesIds[0] : "")
                }
            }

            // A native style (this app sets none explicitly, so it is
            // whatever Qt Quick Controls resolves to on the host platform)
            // refuses to let a `CheckBox` customize its `contentItem` --
            // overriding it to wrap this long acknowledgement text produced
            // a `QML Label: The current style does not support
            // customization of this control` warning and, on a style that
            // truly ignores the override, would silently not wrap at all.
            // A plain `CheckBox` also cannot wrap its own built-in label.
            // Splitting the checkbox itself (indicator only, text left
            // empty) from an ordinary wrapping `Label` beside it sidesteps
            // both problems without touching CheckBox's internals.
            RowLayout {
                id: manualCompatibilityRow
                objectName: "manualCompatibilityRow"
                Layout.fillWidth: true
                visible: coreMaterialPanel.controller !== null
                    && coreMaterialPanel.controller.acknowledgementRequired
                spacing: 8

                CheckBox {
                    id: manualCompatibilityCheckBox
                    objectName: "manualCompatibilityCheckBox"
                    Layout.alignment: Qt.AlignTop
                    checked: coreMaterialPanel.controller !== null
                        && coreMaterialPanel.controller.acknowledged
                    activeFocusOnTab: true
                    Accessible.name: qsTr("I accept that core and material compatibility is my assumption for this manual core")
                    onToggled: coreMaterialPanel.controller.setAcknowledged(checked)
                }
                Label {
                    Layout.fillWidth: true
                    text: qsTr("I accept that core and material compatibility is my assumption for this manual core")
                    wrapMode: Text.WordWrap
                    color: "#1e2b32"
                }
            }

            Button {
                id: clearMaterialButton
                objectName: "clearMaterialButton"
                Layout.fillWidth: true
                text: qsTr("Clear pinned material")
                activeFocusOnTab: true
                enabled: coreMaterialPanel.controller !== null
                    && coreMaterialPanel.controller.selectedMaterial.revisionId !== undefined
                Accessible.name: text
                onClicked: coreMaterialPanel.controller.clearMaterial()
            }

            Button {
                id: openMaterialStudioButton
                objectName: "openMaterialStudioButton"
                Layout.fillWidth: true
                text: qsTr("Open Material Studio")
                activeFocusOnTab: true
                enabled: coreMaterialPanel.controller !== null
                Accessible.name: qsTr("Open Material Studio in a separate window")
                onClicked: coreMaterialPanel.controller.openMaterialStudio()
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#fff4ec"
                radius: 6
                visible: messageLabel.text !== ""
                implicitHeight: messageLabel.implicitHeight + 20

                Label {
                    id: messageLabel
                    objectName: "coreMaterialMessage"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.margins: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: coreMaterialPanel.controller !== null
                        ? coreMaterialPanel.controller.message : ""
                    wrapMode: Text.WordWrap
                    color: "#a45528"
                    Accessible.name: text
                }
            }
        }
    }
}
