import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts

Page {
    id: materialStudioPage
    property var controller: null
    property var editing: controller !== null ? controller.imageEditing : ({})
    property var metadata: editing.metadata || ({})
    property var bhSeries: controller !== null
        ? controller.series.filter(function(item) { return item.kind === "bh-curve" })
        : []

    function fieldText(value) {
        return value === undefined || value === null ? "" : String(value)
    }

    function optionalNumber(text) {
        return text.trim().length === 0 ? Number.NaN : Number(text)
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
        onAccepted: materialStudioPage.controller.importTable(selectedFile.toString())
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
        onAccepted: materialStudioPage.controller.importEditedWorkbook(
            selectedFile.toString()
        )
    }
    FileDialog {
        id: imageSourceDialog
        objectName: "imageSourceDialog"
        title: qsTr("Import a material image or PDF page")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Images and PDF files (*.png *.jpg *.jpeg *.pdf)")]
        onAccepted: materialStudioPage.controller.importSourceImage(
            selectedFile.toString(), pdfPageField.value
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
                objectName: "materialLibraryPane"
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                controller: materialStudioPage.controller
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
                    RowLayout {
                        Layout.fillWidth: true
                        Button {
                            objectName: "saveDraftButton"
                            text: qsTr("Save Draft")
                            enabled: materialStudioPage.controller !== null
                                && materialStudioPage.controller.canSave
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
                        model: materialStudioPage.bhSeries
                        textRole: "seriesId"
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
                                ? materialStudioPage.bhSeries[
                                    projectBhSeriesChoice.currentIndex
                                ].seriesId
                                : ""
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
                        }
                        TextField {
                            id: xUnitField
                            objectName: "xUnitField"
                            text: materialStudioPage.fieldText(materialStudioPage.metadata.xUnit)
                            placeholderText: qsTr("X unit")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("X unit")
                        }
                        TextField {
                            id: yUnitField
                            objectName: "yUnitField"
                            text: materialStudioPage.fieldText(materialStudioPage.metadata.yUnit)
                            placeholderText: qsTr("Y unit")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Y unit")
                        }
                        TextField {
                            id: frequencyConditionField
                            objectName: "frequencyConditionField"
                            text: materialStudioPage.fieldText(
                                materialStudioPage.metadata.frequencyHz
                            )
                            placeholderText: qsTr("Frequency (Hz)")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series frequency in hertz")
                        }
                        TextField {
                            id: temperatureConditionField
                            objectName: "temperatureConditionField"
                            text: materialStudioPage.fieldText(
                                materialStudioPage.metadata.temperatureC
                            )
                            placeholderText: qsTr("Temperature (°C)")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series temperature in degrees Celsius")
                        }
                        TextField {
                            id: dcBiasConditionField
                            objectName: "dcBiasConditionField"
                            text: materialStudioPage.fieldText(
                                materialStudioPage.metadata.dcBiasAPerM
                            )
                            placeholderText: qsTr("DC bias (A/m)")
                            activeFocusOnTab: true
                            Accessible.name: qsTr("Series DC bias in amperes per metre")
                        }
                        Button {
                            objectName: "applySeriesMetadataButton"
                            text: qsTr("Apply series")
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
                            Accessible.name: qsTr("Crop height")
                        }
                        Button {
                            objectName: "applyCropButton"
                            text: qsTr("Apply crop")
                            activeFocusOnTab: true
                            Accessible.name: text
                            onClicked: materialStudioPage.controller.setCrop(
                                Number(cropLeftField.text),
                                Number(cropTopField.text),
                                Number(cropWidthField.text),
                                Number(cropHeightField.text)
                            )
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
