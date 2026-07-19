import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Page {
    id: materialStudioPage
    property var controller: null
    property var transactionHost: null
    property string pendingLibrarySelectionKind: ""
    property var pendingLibrarySelectionArguments: []
    property var confirmedMaterialSelection: []
    property var confirmedRevisionSelection: []
    property var editing: controller !== null ? controller.imageEditing : ({})
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

    function applyClampedCrop() {
        const source = controller !== null ? controller.source : ({})
        const sourceWidth = Math.max(1, Math.round(Number(source.width) || 1))
        const sourceHeight = Math.max(1, Math.round(Number(source.height) || 1))
        const rawLeft = Math.round(Number(cropLeftField.text))
        const rawTop = Math.round(Number(cropTopField.text))
        const rawWidth = Math.round(Number(cropWidthField.text))
        const rawHeight = Math.round(Number(cropHeightField.text))
        const left = Math.max(
            0, Math.min(Number.isFinite(rawLeft) ? rawLeft : 0, sourceWidth - 1)
        )
        const top = Math.max(
            0, Math.min(Number.isFinite(rawTop) ? rawTop : 0, sourceHeight - 1)
        )
        const width = Math.max(
            1,
            Math.min(Number.isFinite(rawWidth) ? rawWidth : 1, sourceWidth - left)
        )
        const height = Math.max(
            1,
            Math.min(Number.isFinite(rawHeight) ? rawHeight : 1, sourceHeight - top)
        )
        controller.setCrop(left, top, width, height)
    }

    function conditionText(value, unit) {
        return value === undefined || value === null
            ? qsTr("unspecified")
            : qsTr("%1 %2").arg(value).arg(unit)
    }

    function sourceTraceText(source) {
        const page = source.page === undefined || source.page === null
            ? qsTr("unspecified") : String(source.page)
        return [
            qsTr("Source: %1").arg(source.filename),
            qsTr("URL: %1").arg(source.url),
            qsTr("Page: %1").arg(page),
            qsTr("Captured: %1").arg(source.capturedAt),
            qsTr("Description: %1").arg(source.description),
            qsTr("SHA-256: %1").arg(source.sha256)
        ].join("\n")
    }

    function sourcesTraceText() {
        return revisionSources.map(function(source) {
            return sourceTraceText(source)
        }).join("\n\n")
    }

    function markPendingEditorInput(group) {
        if (controller !== null) {
            controller.invalidateEditorInput(
                group,
                qsTr("Apply or correct the visible editor input before saving.")
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

    function setConfirmedLibrarySelection(kind, selectionArguments) {
        if (kind === "material") {
            confirmedMaterialSelection = selectionArguments
            confirmedRevisionSelection = selectionArgumentsAt("revision", 0)
        } else {
            confirmedRevisionSelection = selectionArguments
        }
    }

    function restoreLibrarySelection(kind, selectionArguments) {
        const list = libraryList(kind)
        const index = selectionIndex(kind, selectionArguments)
        if (list !== null) {
            list.currentIndex = index
        }
    }

    function syncLibrarySelectionFromController() {
        if (controller === null) {
            return
        }
        const selectedMaterial = controller.selectedMaterial || ({})
        const materialSelection = [
            selectedMaterial.manufacturer,
            selectedMaterial.name,
            selectedMaterial.grade
        ]
        if (materialSelection.every(function(value) {
            return value !== undefined && value !== null && String(value).length > 0
        }) && selectionIndex("material", materialSelection) >= 0) {
            confirmedMaterialSelection = materialSelection
            restoreLibrarySelection("material", materialSelection)
        } else {
            confirmedMaterialSelection = []
            confirmedRevisionSelection = []
            const materialList = libraryList("material")
            const revisionList = libraryList("revision")
            if (materialList !== null) {
                materialList.currentIndex = -1
            }
            if (revisionList !== null) {
                revisionList.currentIndex = -1
            }
            return
        }
        const selected = controller.selectedRevision || ({})
        const revisionSelection = [selected.revisionId]
        if (selected.revisionId !== undefined && selected.revisionId !== null
                && String(selected.revisionId).length > 0
                && selectionIndex("revision", revisionSelection) >= 0) {
            confirmedRevisionSelection = revisionSelection
            restoreLibrarySelection("revision", revisionSelection)
        } else {
            confirmedRevisionSelection = []
            const revisionList = libraryList("revision")
            if (revisionList !== null) {
                revisionList.currentIndex = -1
            }
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
            setConfirmedLibrarySelection(selectionKind, selectionArguments)
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
        } else if (action === "importSourceImage") {
            controller.importSourceImage(arguments_[0], arguments_[1])
        }
    }

    Component.onCompleted: {
        confirmedMaterialSelection = selectionArgumentsAt("material", 0)
        confirmedRevisionSelection = selectionArgumentsAt("revision", 0)
        syncLibrarySelectionFromController()
    }

    Connections {
        target: materialStudioPage.controller

        function onLibraryChanged() {
            Qt.callLater(materialStudioPage.syncLibrarySelectionFromController)
        }

        function onSelectionChanged() {
            Qt.callLater(materialStudioPage.syncLibrarySelectionFromController)
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
    FileDialog {
        id: imageSourceDialog
        objectName: "imageSourceDialog"
        title: qsTr("Import a material image or PDF page")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Images and PDF files (*.png *.jpg *.jpeg *.pdf)")]
        onAccepted: materialStudioPage.requestDestructiveAction(
            "importSourceImage", [selectedFile.toString(), pdfPageField.value]
        )
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Label {
            text: qsTr("Material Studio")
            font.pixelSize: 22
            font.bold: true
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 238
            spacing: 8

            MaterialLibraryPane {
                id: materialLibraryPane
                objectName: "materialLibraryPane"
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                controller: libraryController
            }

            Pane {
                objectName: "materialImportExportPane"
                Layout.preferredWidth: 245
                Layout.fillHeight: true
                Accessible.name: qsTr("Material import and export")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4

                    Label { text: qsTr("Import and export"); font.bold: true }
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
                        text: qsTr("Upload table")
                        activeFocusOnTab: true
                        Accessible.name: qsTr("Upload CSV or XLSX")
                        onClicked: tableUploadDialog.open()
                    }
                    Button {
                        objectName: "exportRevisionButton"
                        Layout.fillWidth: true
                        text: qsTr("Export selected revision")
                        enabled: materialStudioPage.controller !== null
                            && Object.keys(materialStudioPage.controller.selectedRevision).length > 0
                        activeFocusOnTab: true
                        Accessible.name: qsTr("Export selected revision")
                        onClicked: revisionExportDialog.open()
                    }
                    Button {
                        objectName: "reimportWorkbookButton"
                        Layout.fillWidth: true
                        text: qsTr("Reimport edited workbook")
                        activeFocusOnTab: true
                        Accessible.name: qsTr("Reimport edited workbook")
                        onClicked: workbookReimportDialog.open()
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            objectName: "importImageButton"
                            Layout.fillWidth: true
                            text: qsTr("Import image/PDF")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Import PNG, JPEG, or PDF page")
                            onClicked: imageSourceDialog.open()
                        }
                        SpinBox {
                            id: pdfPageField
                            objectName: "pdfPageField"
                            from: 0
                            to: 999
                            value: 0
                            editable: true
                            activeFocusOnTab: true
                            Accessible.name: qsTr("PDF page, zero based")
                        }
                    }
                }
            }

            Pane {
                objectName: "materialLifecyclePane"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Accessible.name: qsTr("Material lifecycle and project selection")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 4
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
                        Accessible.name: qsTr("Selected revision source traceability")

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
                            text: qsTr("Save Draft")
                            enabled: materialStudioPage.controller !== null
                                && materialStudioPage.controller.canSave
                                && materialStudioPage.seriesMetadataInputsValid
                            activeFocusOnTab: true
                            Accessible.name: text
                            onClicked: materialStudioPage.controller.saveDraft()
                        }
                        Button {
                            objectName: "reviewDraftButton"
                            text: qsTr("Review")
                            enabled: materialStudioPage.controller !== null
                                && materialStudioPage.controller.canReview
                                && reviewerField.text.trim().length > 0
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Review material draft")
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
                            Accessible.name: qsTr("Approve material revision")
                            onClicked: materialStudioPage.controller.approveRevision(
                                approverField.text
                            )
                        }
                    }
                    Label {
                        text: qsTr("B-H series for project")
                        Accessible.name: text
                    }
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
                        text: qsTr("Use in Project")
                        enabled: materialStudioPage.controller !== null
                            && materialStudioPage.controller.canUseInProject
                            && (projectBhSeriesChoice.count <= 1
                                || projectBhSeriesChoice.currentIndex >= 0)
                        activeFocusOnTab: true
                        Accessible.name: qsTr("Use approved B-H material in project")
                        onClicked: materialStudioPage.controller.useInProject(
                            projectBhSeriesChoice.currentIndex >= 0
                                ? projectBhSeriesChoice.currentValue : ""
                        )
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Pane {
                objectName: "materialSourceCurveWorkspace"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Accessible.name: qsTr("Material source and curve workspace")

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 5

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Identity:") }
                        TextField {
                            id: manufacturerField
                            objectName: "imageManufacturerField"
                            Layout.fillWidth: true
                            placeholderText: qsTr("Manufacturer")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Image draft manufacturer")
                        }
                        TextField {
                            id: materialNameField
                            objectName: "imageMaterialNameField"
                            Layout.fillWidth: true
                            placeholderText: qsTr("Material name")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Image draft material name")
                        }
                        TextField {
                            id: gradeField
                            objectName: "imageGradeField"
                            Layout.fillWidth: true
                            placeholderText: qsTr("Grade")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Image draft grade")
                        }
                        TextField {
                            id: sourceDescriptionField
                            objectName: "sourceDescriptionField"
                            Layout.fillWidth: true
                            placeholderText: qsTr("Source description")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Source description")
                        }
                        Button {
                            objectName: "createImageDraftButton"
                            text: qsTr("Create image draft")
                            enabled: materialStudioPage.controller !== null
                                && Object.keys(materialStudioPage.controller.source).length > 0
                                && manufacturerField.text.trim().length > 0
                                && materialNameField.text.trim().length > 0
                                && gradeField.text.trim().length > 0
                            activeFocusOnTab: true
                            Accessible.name: text
                            onClicked: materialStudioPage.controller.createImageDraft(
                                manufacturerField.text,
                                materialNameField.text,
                                gradeField.text,
                                sourceDescriptionField.text
                            )
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: qsTr("Series management")
                            font.bold: true
                        }
                        TextField {
                            id: newSeriesIdField
                            objectName: "newSeriesIdField"
                            Layout.preferredWidth: 115
                            placeholderText: qsTr("New series ID")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("New series ID")
                        }
                        TextArea {
                            id: newSeriesPointsField
                            objectName: "newSeriesPointsField"
                            Layout.fillWidth: true
                            Layout.preferredHeight: 46
                            placeholderText: qsTr("Table points: one x,y pair per line")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("New table series points")
                        }
                        Button {
                            objectName: "addTableSeriesButton"
                            text: qsTr("Add table")
                            enabled: newSeriesIdField.text.trim().length > 0
                                && materialStudioPage.seriesMetadataInputsValid
                                && materialStudioPage.parseSeriesPoints(
                                    newSeriesPointsField.text
                                ).length > 0
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Add table series with explicit points")
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
                            objectName: "addImageSeriesButton"
                            text: qsTr("Add image/PDF")
                            enabled: newSeriesIdField.text.trim().length > 0
                                && materialStudioPage.seriesMetadataInputsValid
                                && materialStudioPage.controller !== null
                                && Object.keys(materialStudioPage.controller.source).length > 0
                            activeFocusOnTab: true
                            Accessible.name: qsTr(
                                "Add another digitized series from the current calibrated source"
                            )
                            onClicked: materialStudioPage.controller.addImageSeries(
                                newSeriesIdField.text,
                                seriesKindField.currentValue,
                                xUnitField.text,
                                yUnitField.text,
                                materialStudioPage.optionalNumber(frequencyConditionField.text),
                                materialStudioPage.optionalNumber(temperatureConditionField.text),
                                materialStudioPage.optionalNumber(dcBiasConditionField.text)
                            )
                        }
                        Button {
                            objectName: "removeSeriesButton"
                            text: qsTr("Remove selected")
                            enabled: workspaceSeriesChoice.currentIndex >= 0
                                && workspaceSeriesChoice.count > 1
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Remove selected non-final series")
                            onClicked: materialStudioPage.controller.removeSeries(
                                workspaceSeriesChoice.currentValue
                            )
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        ComboBox {
                            id: workspaceSeriesChoice
                            objectName: "workspaceSeriesChoice"
                            Layout.preferredWidth: 110
                            model: materialStudioPage.controller !== null
                                ? materialStudioPage.controller.series
                                : []
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
                            Accessible.name: qsTr("Series to edit")
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
                            Accessible.name: qsTr("Series ID")
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
                                ? 1
                                : 0
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series kind")
                            onActivated: materialStudioPage.markPendingEditorInput("metadata")
                        }
                        TextField {
                            id: xUnitField
                            objectName: "xUnitField"
                            text: materialStudioPage.fieldText(materialStudioPage.metadata.xUnit)
                            placeholderText: qsTr("X unit")
                            onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("X unit")
                        }
                        TextField {
                            id: yUnitField
                            objectName: "yUnitField"
                            text: materialStudioPage.fieldText(materialStudioPage.metadata.yUnit)
                            placeholderText: qsTr("Y unit")
                            onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Y unit")
                        }
                        TextField {
                            id: frequencyConditionField
                            objectName: "frequencyConditionField"
                            property bool parseValid: materialStudioPage.optionalNumberValid(text)
                            text: materialStudioPage.fieldText(
                                materialStudioPage.metadata.frequencyHz
                            )
                            placeholderText: qsTr("Frequency (Hz)")
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series frequency in hertz")
                        }
                        TextField {
                            id: temperatureConditionField
                            objectName: "temperatureConditionField"
                            property bool parseValid: materialStudioPage.optionalNumberValid(text)
                            text: materialStudioPage.fieldText(
                                materialStudioPage.metadata.temperatureC
                            )
                            placeholderText: qsTr("Temperature (°C)")
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series temperature in degrees Celsius")
                        }
                        TextField {
                            id: dcBiasConditionField
                            objectName: "dcBiasConditionField"
                            property bool parseValid: materialStudioPage.optionalNumberValid(text)
                            text: materialStudioPage.fieldText(
                                materialStudioPage.metadata.dcBiasAPerM
                            )
                            placeholderText: qsTr("DC bias (A/m)")
                            inputMethodHints: Qt.ImhFormattedNumbersOnly
                            onTextEdited: materialStudioPage.markPendingEditorInput("metadata")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series DC bias in amperes per metre")
                        }
                        Button {
                            objectName: "applySeriesMetadataButton"
                            text: qsTr("Apply series")
                            enabled: materialStudioPage.seriesMetadataInputsValid
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Apply series metadata and conditions")
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
                        color: palette.text
                        font.bold: true
                        text: qsTr(
                            "Series ID and units are required; each nonblank condition must be a valid number."
                        )
                        wrapMode: Text.WordWrap
                        Accessible.name: text
                        Accessible.ignored: !visible
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Crop") }
                        TextField {
                            id: cropLeftField
                            objectName: "cropLeftField"
                            Layout.preferredWidth: 62
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.crop || ({})).left
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("crop")
                            Accessible.name: qsTr("Crop left")
                        }
                        TextField {
                            id: cropTopField
                            objectName: "cropTopField"
                            Layout.preferredWidth: 62
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.crop || ({})).top
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("crop")
                            Accessible.name: qsTr("Crop top")
                        }
                        TextField {
                            id: cropWidthField
                            objectName: "cropWidthField"
                            Layout.preferredWidth: 62
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.crop || ({})).width
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("crop")
                            Accessible.name: qsTr("Crop width")
                        }
                        TextField {
                            id: cropHeightField
                            objectName: "cropHeightField"
                            Layout.preferredWidth: 62
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.crop || ({})).height
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("crop")
                            Accessible.name: qsTr("Crop height")
                        }
                        Button {
                            objectName: "applyCropButton"
                            text: qsTr("Apply crop")
                            activeFocusOnTab: true
                            Accessible.name: text
                            onClicked: materialStudioPage.applyClampedCrop()
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("X axis") }
                        ComboBox {
                            id: xAxisScaleField
                            objectName: "xAxisScaleField"
                            Layout.preferredWidth: 78
                            model: [
                                {"value": "linear", "label": qsTr("Linear")},
                                {"value": "log", "label": qsTr("Logarithmic")}
                            ]
                            textRole: "label"
                            valueRole: "value"
                            currentIndex: (materialStudioPage.editing.xAxis || ({})).scale
                                === "log" ? 1 : 0
                            activeFocusOnTab: true
                            onActivated: materialStudioPage.markPendingEditorInput("x-axis")
                            Accessible.name: qsTr("X axis scale")
                        }
                        TextField {
                            id: xAxisPixelAField
                            objectName: "xAxisPixelAField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.xAxis || ({})).pixelA
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("x-axis")
                            Accessible.name: qsTr("X axis anchor A pixel")
                        }
                        TextField {
                            id: xAxisValueAField
                            objectName: "xAxisValueAField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.xAxis || ({})).valueA
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("x-axis")
                            Accessible.name: qsTr("X axis anchor A value")
                        }
                        TextField {
                            id: xAxisPixelBField
                            objectName: "xAxisPixelBField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.xAxis || ({})).pixelB
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("x-axis")
                            Accessible.name: qsTr("X axis anchor B pixel")
                        }
                        TextField {
                            id: xAxisValueBField
                            objectName: "xAxisValueBField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.xAxis || ({})).valueB
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("x-axis")
                            Accessible.name: qsTr("X axis anchor B value")
                        }
                        Button {
                            objectName: "applyXAxisButton"
                            text: qsTr("Apply X axis")
                            activeFocusOnTab: true
                            Accessible.name: text
                            onClicked: materialStudioPage.controller.setXAxis(
                                xAxisScaleField.currentValue,
                                Number(xAxisPixelAField.text),
                                Number(xAxisValueAField.text),
                                Number(xAxisPixelBField.text),
                                Number(xAxisValueBField.text)
                            )
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: qsTr("Y axis") }
                        ComboBox {
                            id: yAxisScaleField
                            objectName: "yAxisScaleField"
                            Layout.preferredWidth: 78
                            model: [
                                {"value": "linear", "label": qsTr("Linear")},
                                {"value": "log", "label": qsTr("Logarithmic")}
                            ]
                            textRole: "label"
                            valueRole: "value"
                            currentIndex: (materialStudioPage.editing.yAxis || ({})).scale
                                === "log" ? 1 : 0
                            activeFocusOnTab: true
                            onActivated: materialStudioPage.markPendingEditorInput("y-axis")
                            Accessible.name: qsTr("Y axis scale")
                        }
                        TextField {
                            id: yAxisPixelAField
                            objectName: "yAxisPixelAField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.yAxis || ({})).pixelA
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("y-axis")
                            Accessible.name: qsTr("Y axis anchor A pixel")
                        }
                        TextField {
                            id: yAxisValueAField
                            objectName: "yAxisValueAField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.yAxis || ({})).valueA
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("y-axis")
                            Accessible.name: qsTr("Y axis anchor A value")
                        }
                        TextField {
                            id: yAxisPixelBField
                            objectName: "yAxisPixelBField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.yAxis || ({})).pixelB
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("y-axis")
                            Accessible.name: qsTr("Y axis anchor B pixel")
                        }
                        TextField {
                            id: yAxisValueBField
                            objectName: "yAxisValueBField"
                            Layout.preferredWidth: 55
                            text: materialStudioPage.fieldText(
                                (materialStudioPage.editing.yAxis || ({})).valueB
                            )
                            activeFocusOnTab: true
                            onTextEdited: materialStudioPage.markPendingEditorInput("y-axis")
                            Accessible.name: qsTr("Y axis anchor B value")
                        }
                        Button {
                            objectName: "applyYAxisButton"
                            text: qsTr("Apply Y axis")
                            activeFocusOnTab: true
                            Accessible.name: text
                            onClicked: materialStudioPage.controller.setYAxis(
                                yAxisScaleField.currentValue,
                                Number(yAxisPixelAField.text),
                                Number(yAxisValueAField.text),
                                Number(yAxisPixelBField.text),
                                Number(yAxisValueBField.text)
                            )
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        MaterialSourceView {
                            objectName: "materialSourceView"
                            Layout.preferredWidth: 1
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            activeFocusOnTab: true
                            controller: materialStudioPage.controller
                        }
                        MaterialCurveEditor {
                            objectName: "materialCurveEditor"
                            Layout.preferredWidth: 1
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            controller: materialStudioPage.controller
                        }
                    }
                }
            }

            MaterialValidationPane {
                objectName: "materialValidationPane"
                Layout.preferredWidth: 270
                Layout.fillHeight: true
                controller: materialStudioPage.controller
            }
        }

        Label {
            objectName: "materialStatusText"
            Layout.fillWidth: true
            text: materialStudioPage.controller !== null
                ? materialStudioPage.controller.statusMessage
                : qsTr("")
            wrapMode: Text.WordWrap
            Accessible.name: text.length > 0
                ? qsTr("Material Studio status: %1").arg(text)
                : qsTr("Material Studio status")
        }
    }

}
