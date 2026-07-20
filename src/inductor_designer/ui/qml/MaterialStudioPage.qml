import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Page {
    id: materialStudioPage
    property var controller: null
    property var transactionHost: null
    property var editing: controller !== null ? controller.tableEditing : ({})
    property var metadata: editing.metadata || ({})
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
    property bool seriesMetadataInputsValid:
        seriesIdField.text.trim().length > 0
        && xUnitField.text.trim().length > 0
        && yUnitField.text.trim().length > 0
        && frequencyConditionField.parseValid
        && temperatureConditionField.parseValid
        && dcBiasConditionField.parseValid
    property int overviewColumns: width < 1000 ? 1 : width < 1400 ? 2 : 3
    property int workspaceColumns: width < 1200 ? 1 : 2
    property int workspaceFormColumns: width < 1800 ? 4 : 6

    function fieldText(value) {
        return value === undefined || value === null ? "" : String(value)
    }

    function optionalNumber(text) {
        return text.trim().length === 0 ? Number.NaN : Number(text)
    }

    function optionalNumberValid(text) {
        return text.trim().length === 0 || Number.isFinite(Number(text))
    }

    function parseSeriesPoints(text) {
        const lines = text.split(/\r?\n/).filter(function(line) {
            return line.trim().length > 0
        })
        const points = []
        for (let index = 0; index < lines.length; ++index) {
            const values = lines[index].split(",")
            if (values.length !== 2) {
                return []
            }
            const x = Number(values[0].trim())
            const y = Number(values[1].trim())
            if (!Number.isFinite(x) || !Number.isFinite(y)) {
                return []
            }
            points.push({"x": x, "y": y})
        }
        return points
    }

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
            ? revisionSources.map(function(source) {
                return sourceTraceText(source)
            }).join("\n\n")
            : qsTr("No material table has been imported yet.")
    }

    function markPendingEditorInput(group) {
        if (controller !== null) {
            controller.invalidateEditorInput(
                group,
                qsTr("Apply or correct the visible table field before saving.")
            )
        }
    }

    function findNamedChild(item, name) {
        if (item === null || item === undefined) {
            return null
        }
        if (item.objectName === name) {
            return item
        }
        const childItems = item.children || []
        for (let index = 0; index < childItems.length; ++index) {
            const found = findNamedChild(childItems[index], name)
            if (found !== null) {
                return found
            }
        }
        return null
    }

    function libraryList(kind) {
        return findNamedChild(
            materialLibraryPane,
            kind === "material" ? "materialList" : "revisionList"
        )
    }

    function selectionArgumentsAt(kind, index) {
        const values = kind === "material"
            ? libraryController.materials : libraryController.revisions
        if (index < 0 || index >= values.length) {
            return []
        }
        const value = values[index]
        return kind === "material"
            ? [value.manufacturer, value.name, value.grade]
            : [value.revisionId]
    }

    function selectionIndex(kind, selectionArguments) {
        const values = kind === "material"
            ? libraryController.materials : libraryController.revisions
        for (let index = 0; index < values.length; ++index) {
            const candidate = selectionArgumentsAt(kind, index)
            if (candidate.length === selectionArguments.length
                    && candidate.every(function(value, part) {
                        return value === selectionArguments[part]
                    })) {
                return index
            }
        }
        return -1
    }

    function confirmedLibrarySelection(kind) {
        return kind === "material"
            ? confirmedMaterialSelection : confirmedRevisionSelection
    }

    function restoreLibrarySelection(kind, selectionArguments) {
        const list = libraryList(kind)
        const index = selectionIndex(kind, selectionArguments)
        if (list !== null) {
            list.currentIndex = index
        }
    }

    function performLibrarySelection(selectionKind, selectionArguments) {
        let selected = false
        if (selectionKind === "material") {
            selected = controller.selectMaterial(
                selectionArguments[0], selectionArguments[1], selectionArguments[2]
            )
        } else if (selectionKind === "revision") {
            selected = controller.selectRevision(selectionArguments[0])
        }
        if (selected) {
            if (selectionKind === "material") {
                confirmedMaterialSelection = selectionArguments
                confirmedRevisionSelection = []
            } else {
                confirmedRevisionSelection = selectionArguments
            }
        }
        restoreLibrarySelection(
            selectionKind,
            selected ? selectionArguments : confirmedLibrarySelection(selectionKind)
        )
    }

    function requestLibrarySelection(kind, selectionArguments) {
        restoreLibrarySelection(kind, confirmedLibrarySelection(kind))
        transactionHost.requestMaterialAction(
            "librarySelection", [kind, selectionArguments]
        )
    }

    function requestDestructiveAction(action, arguments_) {
        transactionHost.requestMaterialAction(action, arguments_)
    }

    function performTransactionAction(action, arguments_) {
        if (action === "librarySelection") {
            performLibrarySelection(arguments_[0], arguments_[1])
        } else if (action === "importTable") {
            controller.importTable(arguments_[0])
        } else if (action === "importEditedWorkbook") {
            controller.importEditedWorkbook(arguments_[0])
        }
    }

    property var confirmedMaterialSelection: []
    property var confirmedRevisionSelection: []

    Component.onCompleted: {
        confirmedMaterialSelection = selectionArgumentsAt("material", 0)
        confirmedRevisionSelection = selectionArgumentsAt("revision", 0)
    }

    Connections {
        target: materialStudioPage.controller
        function onLibraryChanged() {
            Qt.callLater(function() {
                materialStudioPage.revisionSources = materialStudioPage.controller !== null
                    ? (materialStudioPage.controller.selectedRevision["sources"] || [])
                    : []
            })
        }
    }

    QtObject {
        id: libraryController
        property var materials: materialStudioPage.controller !== null
            ? materialStudioPage.controller.materials : []
        property var revisions: materialStudioPage.controller !== null
            ? materialStudioPage.controller.revisions : []

        function selectMaterial(manufacturer, name, grade) {
            materialStudioPage.requestLibrarySelection(
                "material", [manufacturer, name, grade]
            )
        }

        function selectRevision(revisionId) {
            materialStudioPage.requestLibrarySelection("revision", [revisionId])
        }
    }

    padding: 10

    FileDialog {
        id: templateCsvDialog
        objectName: "templateCsvDialog"
        title: qsTr("Save CSV material template")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("CSV files (*.csv)")]
        defaultSuffix: "csv"
        onAccepted: materialStudioPage.controller.downloadTemplate(
            "csv", selectedFile.toString()
        )
    }
    FileDialog {
        id: templateXlsxDialog
        objectName: "templateXlsxDialog"
        title: qsTr("Save XLSX material template")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Excel workbooks (*.xlsx)")]
        defaultSuffix: "xlsx"
        onAccepted: materialStudioPage.controller.downloadTemplate(
            "xlsx", selectedFile.toString()
        )
    }
    FileDialog {
        id: tableUploadDialog
        objectName: "tableUploadDialog"
        title: qsTr("Upload a material table")
        fileMode: FileDialog.OpenFile
        nameFilters: [
            qsTr("Material tables (*.csv *.xlsx)"),
            qsTr("CSV files (*.csv)"),
            qsTr("Excel workbooks (*.xlsx)")
        ]
        onAccepted: materialStudioPage.requestDestructiveAction(
            "importTable", [selectedFile.toString()]
        )
    }
    FileDialog {
        id: revisionExportDialog
        objectName: "revisionExportDialog"
        title: qsTr("Export the selected material revision")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("Excel workbooks (*.xlsx)")]
        defaultSuffix: "xlsx"
        onAccepted: materialStudioPage.controller.exportSelectedWorkbook(
            selectedFile.toString()
        )
    }
    FileDialog {
        id: workbookReimportDialog
        objectName: "workbookReimportDialog"
        title: qsTr("Reimport an edited material workbook")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Excel workbooks (*.xlsx)")]
        onAccepted: materialStudioPage.requestDestructiveAction(
            "importEditedWorkbook", [selectedFile.toString()]
        )
    }

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
                    "Workflow: 1. Download a CSV or XLSX template. 2. Fill the material metadata and curve tables. 3. Upload the table. 4. Select a revision and series to inspect the plotted canonical curve."
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
                    Accessible.name: qsTr("Material table import and export")

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6
                        Label { text: qsTr("Table import and export"); font.bold: true }
                        Label {
                            Layout.fillWidth: true
                            text: qsTr(
                                "Use CSV for a compact exchange or XLSX for the structured workbook. These are the only supported material inputs."
                            )
                            wrapMode: Text.WordWrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button {
                                objectName: "downloadCsvTemplateButton"
                                Layout.fillWidth: true
                                text: qsTr("CSV template")
                                activeFocusOnTab: true
                                Accessible.name: qsTr("Download CSV template")
                                onClicked: templateCsvDialog.open()
                            }
                            Button {
                                objectName: "downloadXlsxTemplateButton"
                                Layout.fillWidth: true
                                text: qsTr("XLSX template")
                                activeFocusOnTab: true
                                Accessible.name: qsTr("Download XLSX template")
                                onClicked: templateXlsxDialog.open()
                            }
                        }
                        Button {
                            objectName: "uploadTableButton"
                            Layout.fillWidth: true
                            text: qsTr("Upload CSV or XLSX")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Upload a CSV or XLSX material table")
                            onClicked: tableUploadDialog.open()
                        }
                        Button {
                            objectName: "exportRevisionButton"
                            Layout.fillWidth: true
                            text: qsTr("Export selected revision")
                            enabled: materialStudioPage.controller !== null
                                && Object.keys(materialStudioPage.controller.selectedRevision).length > 0
                            activeFocusOnTab: true
                            onClicked: revisionExportDialog.open()
                        }
                        Button {
                            objectName: "reimportWorkbookButton"
                            Layout.fillWidth: true
                            text: qsTr("Reimport edited XLSX")
                            activeFocusOnTab: true
                            onClicked: workbookReimportDialog.open()
                        }
                    }
                }

                Pane {
                    objectName: "materialLifecyclePane"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: 250
                    Accessible.name: qsTr("Material lifecycle and project selection")

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 5
                        Label { text: qsTr("Lifecycle and project"); font.bold: true }
                        RowLayout {
                            Layout.fillWidth: true
                            TextField {
                                id: reviewerField
                                objectName: "reviewerField"
                                Layout.fillWidth: true
                                placeholderText: qsTr("Reviewer identity")
                                activeFocusOnTab: true
                                Accessible.name: qsTr("Reviewer identity")
                            }
                            TextField {
                                id: approverField
                                objectName: "approverField"
                                Layout.fillWidth: true
                                placeholderText: qsTr("Approver identity")
                                activeFocusOnTab: true
                                Accessible.name: qsTr("Approver identity")
                            }
                        }
                        ScrollView {
                            objectName: "materialTraceabilityRegion"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 74
                            clip: true
                            Label {
                                objectName: "materialSourceTraceabilityDetails"
                                width: parent.width
                                text: materialStudioPage.sourcesTraceText()
                                wrapMode: Text.WrapAnywhere
                                Accessible.name: text
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Button {
                                objectName: "saveDraftButton"
                                text: qsTr("Save draft")
                                enabled: materialStudioPage.controller !== null
                                    && materialStudioPage.controller.canSave
                                    && materialStudioPage.seriesMetadataInputsValid
                                activeFocusOnTab: true
                                onClicked: materialStudioPage.controller.saveDraft()
                            }
                            Button {
                                objectName: "reviewDraftButton"
                                text: qsTr("Review")
                                enabled: materialStudioPage.controller !== null
                                    && materialStudioPage.controller.canReview
                                    && reviewerField.text.trim().length > 0
                                activeFocusOnTab: true
                                onClicked: materialStudioPage.controller.reviewDraft(
                                    reviewerField.text
                                )
                            }
                            Button {
                                objectName: "approveRevisionButton"
                                text: qsTr("Approve")
                                enabled: materialStudioPage.controller !== null
                                    && materialStudioPage.controller.canApprove
                                    && approverField.text.trim().length > 0
                                activeFocusOnTab: true
                                onClicked: materialStudioPage.controller.approveRevision(
                                    approverField.text
                                )
                            }
                        }
                        Label { text: qsTr("B-H series for project") }
                        ComboBox {
                            id: projectBhSeriesChoice
                            objectName: "projectBhSeriesChoice"
                            Layout.fillWidth: true
                            model: materialStudioPage.bhSeriesOptions
                            textRole: "label"
                            valueRole: "seriesId"
                            currentIndex: count === 1 ? 0 : -1
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Explicit B-H series for project")
                        }
                        Button {
                            objectName: "useInProjectButton"
                            Layout.fillWidth: true
                            text: qsTr("Use in project")
                            enabled: materialStudioPage.controller !== null
                                && materialStudioPage.controller.canUseInProject
                                && (projectBhSeriesChoice.count <= 1
                                    || projectBhSeriesChoice.currentIndex >= 0)
                            activeFocusOnTab: true
                            onClicked: materialStudioPage.controller.useInProject(
                                projectBhSeriesChoice.currentIndex >= 0
                                    ? projectBhSeriesChoice.currentValue : ""
                            )
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
                    Layout.preferredHeight: materialStudioPage.workspaceColumns === 1 ? 920 : 700
                    Accessible.name: qsTr("Material curve workspace")

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6

                        GridLayout {
                            Layout.fillWidth: true
                            columns: materialStudioPage.workspaceFormColumns
                            rowSpacing: 5
                            columnSpacing: 5
                            Label {
                                text: qsTr("Series management")
                                font.bold: true
                                Layout.columnSpan: materialStudioPage.workspaceFormColumns
                            }
                            Label {
                                objectName: "seriesManagementInstructions"
                                Layout.fillWidth: true
                                Layout.columnSpan: materialStudioPage.workspaceFormColumns
                                text: qsTr(
                                    "Select a series to inspect its plot. Add another series only from numeric X,Y pairs copied from a CSV or XLSX table."
                                )
                                wrapMode: Text.WordWrap
                            }
                            TextField {
                                id: newSeriesIdField
                                objectName: "newSeriesIdField"
                                Layout.preferredWidth: 120
                                placeholderText: qsTr("New series ID")
                                activeFocusOnTab: true
                            }
                            TextArea {
                                id: newSeriesPointsField
                                objectName: "newSeriesPointsField"
                                Layout.fillWidth: true
                                Layout.preferredHeight: 46
                                placeholderText: qsTr("One numeric x,y pair per line")
                                activeFocusOnTab: true
                            }
                            Button {
                                objectName: "addTableSeriesButton"
                                text: qsTr("Add table series")
                                enabled: newSeriesIdField.text.trim().length > 0
                                    && materialStudioPage.seriesMetadataInputsValid
                                    && materialStudioPage.parseSeriesPoints(
                                        newSeriesPointsField.text
                                    ).length > 0
                                activeFocusOnTab: true
                                onClicked: materialStudioPage.controller.addTableSeries(
                                    newSeriesIdField.text,
                                    seriesKindField.currentValue,
                                    xUnitField.text,
                                    yUnitField.text,
                                    materialStudioPage.optionalNumber(frequencyConditionField.text),
                                    materialStudioPage.optionalNumber(temperatureConditionField.text),
                                    materialStudioPage.optionalNumber(dcBiasConditionField.text),
                                    materialStudioPage.parseSeriesPoints(newSeriesPointsField.text)
                                )
                            }
                            Button {
                                objectName: "removeSeriesButton"
                                text: qsTr("Remove selected")
                                enabled: workspaceSeriesChoice.currentIndex >= 0
                                    && workspaceSeriesChoice.count > 1
                                activeFocusOnTab: true
                                onClicked: materialStudioPage.controller.removeSeries(
                                    workspaceSeriesChoice.currentValue
                                )
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: materialStudioPage.workspaceFormColumns
                            rowSpacing: 5
                            columnSpacing: 5
                            Label {
                                text: qsTr("Series metadata")
                                font.bold: true
                                Layout.columnSpan: materialStudioPage.workspaceFormColumns
                            }
                            Label {
                                objectName: "seriesMetadataInstructions"
                                Layout.fillWidth: true
                                Layout.columnSpan: materialStudioPage.workspaceFormColumns
                                text: qsTr(
                                    "The fields describe the selected table series. Units determine how the imported values are converted to canonical units."
                                )
                                wrapMode: Text.WordWrap
                            }
                            ComboBox {
                                id: workspaceSeriesChoice
                                objectName: "workspaceSeriesChoice"
                                Layout.preferredWidth: 120
                                model: materialStudioPage.controller !== null
                                    ? materialStudioPage.controller.series : []
                                textRole: "seriesId"
                                valueRole: "seriesId"
                                currentIndex: {
                                    for (let index = 0; index < count; ++index) {
                                        if (model[index].seriesId
                                                === materialStudioPage.metadata.seriesId) {
                                            return index
                                        }
                                    }
                                    return count > 0 ? 0 : -1
                                }
                                activeFocusOnTab: true
                                Accessible.name: qsTr("Table series to inspect")
                                onActivated: materialStudioPage.controller.selectSeries(
                                    currentValue
                                )
                            }
                            TextField {
                                id: seriesIdField
                                objectName: "seriesIdField"
                                text: materialStudioPage.fieldText(materialStudioPage.metadata.seriesId)
                                placeholderText: qsTr("Series ID")
                                onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                                activeFocusOnTab: true
                            }
                            ComboBox {
                                id: seriesKindField
                                objectName: "seriesKindField"
                                model: [
                                    {"value": "bh-curve", "label": qsTr("B-H curve")},
                                    {"value": "loss-table", "label": qsTr("Loss table")}
                                ]
                                textRole: "label"
                                valueRole: "value"
                                currentIndex: materialStudioPage.metadata.kind === "loss-table"
                                    ? 1 : 0
                                activeFocusOnTab: true
                            }
                            TextField {
                                id: xUnitField
                                objectName: "xUnitField"
                                text: materialStudioPage.fieldText(materialStudioPage.metadata.xUnit)
                                placeholderText: qsTr("X unit")
                                onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                                activeFocusOnTab: true
                            }
                            TextField {
                                id: yUnitField
                                objectName: "yUnitField"
                                text: materialStudioPage.fieldText(materialStudioPage.metadata.yUnit)
                                placeholderText: qsTr("Y unit")
                                onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                                activeFocusOnTab: true
                            }
                            TextField {
                                id: frequencyConditionField
                                objectName: "frequencyConditionField"
                                property bool parseValid: materialStudioPage.optionalNumberValid(text)
                                text: materialStudioPage.fieldText(materialStudioPage.metadata.frequencyHz)
                                placeholderText: qsTr("Frequency (Hz)")
                                onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                                activeFocusOnTab: true
                            }
                            TextField {
                                id: temperatureConditionField
                                objectName: "temperatureConditionField"
                                property bool parseValid: materialStudioPage.optionalNumberValid(text)
                                text: materialStudioPage.fieldText(materialStudioPage.metadata.temperatureC)
                                placeholderText: qsTr("Temperature (°C)")
                                onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                                activeFocusOnTab: true
                            }
                            TextField {
                                id: dcBiasConditionField
                                objectName: "dcBiasConditionField"
                                property bool parseValid: materialStudioPage.optionalNumberValid(text)
                                text: materialStudioPage.fieldText(materialStudioPage.metadata.dcBiasAPerM)
                                placeholderText: qsTr("DC bias (A/m)")
                                onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                                activeFocusOnTab: true
                            }
                            Button {
                                objectName: "applySeriesMetadataButton"
                                text: qsTr("Apply series")
                                enabled: materialStudioPage.seriesMetadataInputsValid
                                activeFocusOnTab: true
                                onClicked: materialStudioPage.controller.setSeriesMetadata(
                                    seriesIdField.text,
                                    seriesKindField.currentValue,
                                    xUnitField.text,
                                    yUnitField.text,
                                    materialStudioPage.optionalNumber(frequencyConditionField.text),
                                    materialStudioPage.optionalNumber(temperatureConditionField.text),
                                    materialStudioPage.optionalNumber(dcBiasConditionField.text)
                                )
                            }
                        }

                        Label {
                            objectName: "seriesMetadataInputError"
                            Layout.fillWidth: true
                            visible: !materialStudioPage.seriesMetadataInputsValid
                            text: qsTr(
                                "Series ID and units are required; each nonblank condition must be numeric."
                            )
                            wrapMode: Text.WordWrap
                            Accessible.ignored: !visible
                        }

                        MaterialCurveEditor {
                            objectName: "materialCurveEditor"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 360
                            controller: materialStudioPage.controller
                        }
                    }
                }

                MaterialValidationPane {
                    objectName: "materialValidationPane"
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.preferredHeight: materialStudioPage.workspaceColumns === 1 ? 330 : 700
                    controller: materialStudioPage.controller
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
