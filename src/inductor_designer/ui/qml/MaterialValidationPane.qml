import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialValidationPane
    property var controller: null
    property var fitData: controller !== null ? controller.fit : ({})
    property var groupedIssues: controller !== null
        ? sortedIssues(controller.issues)
        : []

    function severityRank(severity) {
        switch (severity) {
        case "error":
            return 0
        case "warning":
            return 1
        case "info":
            return 2
        default:
            return 3
        }
    }

    function severityText(severity) {
        switch (severity) {
        case "error":
            return qsTr("Error")
        case "warning":
            return qsTr("Warning")
        case "info":
            return qsTr("Info")
        default:
            return qsTr("Other")
        }
    }

    function sortedIssues(issues) {
        const result = issues.slice()
        result.sort(function(left, right) {
            const rankDifference = severityRank(left.severity) - severityRank(right.severity)
            return rankDifference !== 0
                ? rankDifference
                : String(left.code).localeCompare(String(right.code))
        })
        return result
    }

    function displayValue(value) {
        return value === undefined || value === null
            ? qsTr("Not available")
            : String(value)
    }

    function hasFit() {
        return Object.keys(fitData).length > 0
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Label {
            text: qsTr("Fit and validation")
            font.bold: true
        }

        GroupBox {
            Layout.fillWidth: true
            title: qsTr("Fit")
            Accessible.name: title

            ColumnLayout {
                anchors.fill: parent

                Label {
                    visible: !materialValidationPane.hasFit()
                    text: qsTr("No fit available")
                    Accessible.name: text
                    Accessible.ignored: !visible
                }
                Label {
                    visible: materialValidationPane.hasFit()
                    text: qsTr("k: %1").arg(
                        materialValidationPane.displayValue(materialValidationPane.fitData.k)
                    )
                    Accessible.name: text
                    Accessible.ignored: !visible
                }
                Label {
                    visible: materialValidationPane.hasFit()
                    text: qsTr("Alpha: %1").arg(
                        materialValidationPane.displayValue(materialValidationPane.fitData.alpha)
                    )
                    Accessible.name: text
                    Accessible.ignored: !visible
                }
                Label {
                    visible: materialValidationPane.hasFit()
                    text: qsTr("Beta: %1").arg(
                        materialValidationPane.displayValue(materialValidationPane.fitData.beta)
                    )
                    Accessible.name: text
                    Accessible.ignored: !visible
                }
                Label {
                    visible: materialValidationPane.hasFit()
                    text: qsTr("RMS relative residual: %1").arg(
                        materialValidationPane.displayValue(
                            materialValidationPane.fitData.rmsRelativeResidual
                        )
                    )
                    Accessible.name: text
                    Accessible.ignored: !visible
                }
                Label {
                    visible: materialValidationPane.hasFit()
                    text: qsTr("Maximum relative residual: %1").arg(
                        materialValidationPane.displayValue(
                            materialValidationPane.fitData.maxRelativeResidual
                        )
                    )
                    Accessible.name: text
                    Accessible.ignored: !visible
                }
            }
        }

        Label { text: qsTr("Validation issues") }

        ListView {
            id: validationIssueList
            objectName: "validationIssueList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 4
            model: materialValidationPane.groupedIssues
            Accessible.name: qsTr("Validation issues grouped by severity")
            section.property: "severity"
            section.criteria: ViewSection.FullString
            section.delegate: Label {
                required property string section
                width: ListView.view.width
                text: materialValidationPane.severityText(section)
                font.bold: true
                Accessible.name: text
            }

            delegate: Label {
                required property var modelData
                width: ListView.view.width
                text: modelData.message
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
        }
    }
}
