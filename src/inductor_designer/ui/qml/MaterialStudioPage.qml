import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Page {
    id: materialStudioPage
    objectName: "materialStudioPage"
    property var controller: null
    property var transactionHost: null
    property var revisionSources: controller !== null
        ? (controller.selectedRevision["sources"] || []) : []
    property var bhSeries: controller !== null
        ? controller.series.filter(function(item) { return item.kind === "bh-curve" })
        : []
    property var bhSeriesOptions: bhSeries.map(function(item) {
        return {
            "seriesId": item.seriesId,
            "label": qsTr("%1 — temperature %2 — DC bias %3")
                .arg(item.seriesId)
                .arg(conditionText(item.temperatureC, qsTr("°C")))
                .arg(conditionText(item.dcBiasAPerM, qsTr("A/m")))
        }
    })
    property int overviewColumns: width < 1000 ? 1 : width < 1400 ? 2 : 3
    property int workspaceColumns: width < 1200 ? 1 : 2

    function conditionText(value, unit) {
        return value === undefined || value === null
            ? qsTr("unspecified")
            : qsTr("%1 %2").arg(value).arg(unit)
    }

    function sourceTraceText(source) {
        return [
            qsTr("File: %1").arg(source.filename),
            qsTr("Format: %1").arg(source.kind),
            qsTr("URL: %1").arg(source.url || qsTr("not specified")),
            qsTr("Captured: %1").arg(source.capturedAt),
            qsTr("Description: %1").arg(source.description),
            qsTr("SHA-256: %1").arg(source.sha256)
        ].join("\n")
    }

    function sourcesTraceText() {
        return revisionSources.length > 0
            ? revisionSources.map(function(source) { return sourceTraceText(source) }).join("\n\n")
            : qsTr("No material table has been imported yet.")
    }

    function selectionArgumentsAt(index) {
        if (index < 0 || index >= libraryController.materials.length) {
            return []
        }
        const value = libraryController.materials[index]
        return [value.manufacturer, value.name, value.grade]
    }

    function selectionIndex(values) {
        for (let index = 0; index < libraryController.materials.length; ++index) {
            const candidate = selectionArgumentsAt(index)
            if (candidate.length === values.length
                    && candidate.every(function(value, part) { return value === values[part] })) {
                return index
            }
        }
        return -1
    }

    function restoreMaterialSelection(values) {
        if (materialLibraryPane.materialListView !== null) {
            materialLibraryPane.materialListView.currentIndex = selectionIndex(values)
        }
    }

    function performLibrarySelection(values) {
        const selected = controller.selectMaterial(values[0], values[1], values[2])
        if (selected) {
            confirmedMaterialSelection = values
        }
        restoreMaterialSelection(selected ? values : confirmedMaterialSelection)
    }

    function requestLibrarySelection(values) {
        restoreMaterialSelection(confirmedMaterialSelection)
        transactionHost.requestMaterialAction("librarySelection", values)
    }

    function requestMaterialAction(action, values) {
        transactionHost.requestMaterialAction(action, values)
    }

    function performTransactionAction(action, values) {
        if (action === "librarySelection") {
            performLibrarySelection(values)
        } else if (action === "importTable") {
            controller.importTable(values[0])
        } else if (action === "replaceSelectedMaterial") {
            controller.replaceSelectedMaterial(values[0])
        }
    }

    property var confirmedMaterialSelection: []

    QtObject {
        id: libraryController
        property var materials: materialStudioPage.controller !== null
            ? materialStudioPage.controller.materials : []

        function selectMaterial(manufacturer, name, grade) {
            materialStudioPage.requestLibrarySelection([manufacturer, name, grade])
            return true
        }
    }

    Connections {
        target: materialStudioPage.controller
        function onLibraryChanged() {
            materialStudioPage.revisionSources = materialStudioPage.controller !== null
                ? (materialStudioPage.controller.selectedRevision["sources"] || []) : []
        }
        function onSelectionChanged() {
            materialStudioPage.revisionSources = materialStudioPage.controller !== null
                ? (materialStudioPage.controller.selectedRevision["sources"] || []) : []
        }
    }

    Component.onCompleted: {
        confirmedMaterialSelection = selectionArgumentsAt(0)
    }

    FileDialog {
        id: templateCsvDialog
        objectName: "templateCsvDialog"
        title: qsTr("Save CSV material template")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("CSV files (*.csv)")]
        defaultSuffix: "csv"
        onAccepted: controller.downloadTemplate("csv", selectedFile.toString())
    }

    FileDialog {
        id: templateXlsxDialog
        objectName: "templateXlsxDialog"
        title: qsTr("Save XLSX material template")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Excel workbooks (*.xlsx)")]
        defaultSuffix: "xlsx"
        onAccepted: controller.downloadTemplate("xlsx", selectedFile.toString())
    }

    FileDialog {
        id: materialWorkbookDownloadDialog
        objectName: "materialWorkbookDownloadDialog"
        title: qsTr("Save selected material XLSX")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Excel workbooks (*.xlsx)")]
        defaultSuffix: "xlsx"
        onAccepted: controller.exportSelectedWorkbook(selectedFile.toString())
    }

    FileDialog {
        id: tableUploadDialog
        objectName: "tableUploadDialog"
        title: qsTr("Import a material table")
        fileMode: FileDialog.OpenFile
        nameFilters: [
            qsTr("Material tables (*.csv *.xlsx)"),
            qsTr("CSV files (*.csv)"),
            qsTr("Excel workbooks (*.xlsx)")
        ]
        onAccepted: requestMaterialAction("importTable", [selectedFile.toString()])
    }

    FileDialog {
        id: replaceMaterialDialog
        objectName: "replaceMaterialDialog"
        title: qsTr("Replace selected material")
        fileMode: FileDialog.OpenFile
        nameFilters: [
            qsTr("Material tables (*.csv *.xlsx)"),
            qsTr("CSV files (*.csv)"),
            qsTr("Excel workbooks (*.xlsx)")
        ]
        onAccepted: requestMaterialAction("replaceSelectedMaterial", [selectedFile.toString()])
    }

    Dialog {
        id: deleteMaterialDialog
        objectName: "deleteMaterialDialog"
        modal: true
        title: qsTr("Delete selected material")
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: Overlay.overlay

        Label {
            width: 420
            text: qsTr(
                "Delete the selected material and all stored revisions? The original workbook outside the application overlay will not be deleted."
            )
            wrapMode: Text.WordWrap
        }

        onAccepted: controller.deleteSelectedMaterial()
    }

    padding: 10

    ScrollView {
        id: materialStudioScrollView
        objectName: "materialStudioScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        ScrollBar.vertical.policy: ScrollBar.AsNeeded

        ColumnLayout {
            id: materialStudioContent
            width: materialStudioScrollView.availableWidth
            spacing: 12

            Label {
                text: qsTr("Material Studio")
                font.pixelSize: 22
                font.bold: true
            }

            Label {
                objectName: "materialWorkflowGuide"
                Layout.fillWidth: true
                text: qsTr(
                    "Import a completed CSV or XLSX table. Imported revisions are stored immediately and remain read-only; use Replace selected material to provide a new file."
                )
                wrapMode: Text.WordWrap
                Accessible.name: text
            }

            GridLayout {
                id: materialOverviewGrid
                objectName: "materialOverviewGrid"
                Layout.fillWidth: true
                columns: materialStudioPage.overviewColumns
                rowSpacing: 8
                columnSpacing: 8

                MaterialLibraryPane {
                    id: materialLibraryPane
                    objectName: "materialLibraryPane"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 250
                    controller: libraryController
                }

                Pane {
                    objectName: "materialImportExportPane"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 250
                    Accessible.name: qsTr("Material table import and replacement")

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6
                        Label { text: qsTr("Import and replace"); font.bold: true }
                        Label {
                            Layout.fillWidth: true
                            text: qsTr("The Excel and CSV files are the source of truth. The page only checks and visualizes stored data.")
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button {
                                objectName: "downloadCsvTemplateButton"
                                Layout.fillWidth: true
                                text: qsTr("CSV template")
                                onClicked: templateCsvDialog.open()
                            }
                            Button {
                                objectName: "downloadXlsxTemplateButton"
                                Layout.fillWidth: true
                                text: qsTr("XLSX template")
                                onClicked: templateXlsxDialog.open()
                            }
                        }
                        Button {
                            objectName: "uploadTableButton"
                            Layout.fillWidth: true
                            text: qsTr("Import CSV or XLSX")
                            onClicked: tableUploadDialog.open()
                        }
                        Button {
                            objectName: "downloadSelectedMaterialButton"
                            Layout.fillWidth: true
                            text: qsTr("Download selected material XLSX")
                            enabled: controller !== null
                                && Object.keys(controller.selectedRevision).length > 0
                            onClicked: materialWorkbookDownloadDialog.open()
                        }
                        Button {
                            objectName: "replaceSelectedMaterialButton"
                            Layout.fillWidth: true
                            text: qsTr("Replace selected material")
                            enabled: controller !== null && Object.keys(controller.selectedRevision).length > 0
                            onClicked: replaceMaterialDialog.open()
                        }
                        Button {
                            objectName: "deleteSelectedMaterialButton"
                            Layout.fillWidth: true
                            text: qsTr("Delete selected material")
                            enabled: controller !== null && Object.keys(controller.selectedMaterial).length > 0
                            onClicked: deleteMaterialDialog.open()
                        }
                    }
                }

                Pane {
                    objectName: "materialSelectionPane"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 250
                    Accessible.name: qsTr("Material traceability and simulation selection")

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6
                        Label { text: qsTr("Selected revision"); font.bold: true }
                        Label {
                            Layout.fillWidth: true
                            text: controller !== null && controller.selectedRevision.status
                                ? qsTr("Status: %1 · revision %2 · %3 series")
                                    .arg(controller.selectedRevision.status)
                                    .arg(controller.selectedRevision.revisionId)
                                    .arg(controller.selectedRevision.seriesCount)
                                : qsTr("No material revision selected")
                            wrapMode: Text.WordWrap
                        }
                        ScrollView {
                            objectName: "materialTraceabilityRegion"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 90
                            clip: true
                            Label {
                                objectName: "materialSourceTraceabilityDetails"
                                width: parent.width
                                text: materialStudioPage.sourcesTraceText()
                                wrapMode: Text.WrapAnywhere
                                Accessible.name: text
                            }
                        }
                        ComboBox {
                            id: projectBhSeriesChoice
                            objectName: "projectBhSeriesChoice"
                            visible: controller !== null && controller.hasProject
                            Layout.fillWidth: true
                            model: materialStudioPage.bhSeriesOptions
                            textRole: "label"
                            valueRole: "seriesId"
                            currentIndex: count === 1 ? 0 : -1
                            Accessible.name: qsTr("Explicit B-H series for simulation")
                        }
                        Button {
                            id: selectForSimulationButton
                            objectName: "selectForSimulationButton"
                            visible: controller !== null && controller.hasProject
                            Layout.fillWidth: true
                            text: qsTr("Select for simulation")
                            enabled: controller !== null
                                && controller.canUseInProject
                                && (projectBhSeriesChoice.count <= 1
                                    || projectBhSeriesChoice.currentIndex >= 0)
                            onClicked: controller.useInProject(
                                projectBhSeriesChoice.currentIndex >= 0
                                    ? projectBhSeriesChoice.currentValue : ""
                            )
                        }
                        Label {
                            visible: controller === null || !controller.hasProject
                            Layout.fillWidth: true
                            text: qsTr("Load a project to select this revision for simulation.")
                            wrapMode: Text.WordWrap
                            color: palette.mid
                        }
                    }
                }
            }

            GridLayout {
                id: materialWorkspaceGrid
                objectName: "materialWorkspaceGrid"
                Layout.fillWidth: true
                columns: materialStudioPage.workspaceColumns
                rowSpacing: 8
                columnSpacing: 8

                Pane {
                    objectName: "materialCurveWorkspace"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: materialStudioPage.workspaceColumns === 1 ? 640 : 600
                    Accessible.name: qsTr("Material curve workspace")

                    MaterialCurveEditor {
                        objectName: "materialCurveEditor"
                        anchors.fill: parent
                        controller: materialStudioPage.controller
                    }
                }
            }

            Label {
                objectName: "materialStatusText"
                Layout.fillWidth: true
                text: materialStudioPage.controller !== null
                    ? materialStudioPage.controller.statusMessage : qsTr("")
                wrapMode: Text.WordWrap
                Accessible.name: text.length > 0
                    ? qsTr("Material Studio status: %1").arg(text)
                    : qsTr("Material Studio status")
            }
        }
    }
}
