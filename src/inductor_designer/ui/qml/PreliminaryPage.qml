import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: preliminaryPage
    objectName: "preliminaryPage"
    property var controller: null

    function stateColor(state) {
        return state === "estimated" ? "#157a61" : state === "invalid" ? "#a4282d" : "#a45528"
    }

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: preliminaryPage.width - 24
            spacing: 12

            Label {
                Layout.fillWidth: true
                text: qsTr("Design / Preliminary")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Preliminary estimates")
                font.pixelSize: 24
                font.bold: true
                wrapMode: Text.WordWrap
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("Read-only, solver-independent estimates. No Maxwell or FEMM run is started. These values never claim solver accuracy.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }
            Label {
                objectName: "preliminaryMaterialLabel"
                Layout.fillWidth: true
                text: controller === null
                    ? qsTr("No material revision selected")
                    : qsTr("Material revision %1 · B-H series %2")
                        .arg(controller.materialRevisionId === "" ? qsTr("not selected") : controller.materialRevisionId)
                        .arg(controller.bhSeriesId === "" ? qsTr("not selected") : controller.bhSeriesId)
                wrapMode: Text.WordWrap
                color: "#1e2b32"
                Accessible.name: text
            }

            Label { text: qsTr("Core summary"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: coreTable
                objectName: "preliminaryCoreTable"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, count * 40)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.coreRows : []
                Accessible.name: qsTr("Core preliminary results")

                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width
                    height: 40
                    spacing: 8
                    Label {
                        Layout.preferredWidth: 220
                        Layout.minimumWidth: 0
                        text: modelData.label
                        elide: Text.ElideRight
                        color: "#6d7a7e"
                    }
                    Label {
                        Layout.preferredWidth: 140
                        Layout.minimumWidth: 0
                        text: modelData.text
                        elide: Text.ElideRight
                        font.bold: true
                        color: preliminaryPage.stateColor(modelData.state)
                        Accessible.name: qsTr("%1 is %2").arg(modelData.label).arg(modelData.text)
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.code === "" ? "" : qsTr("%1 — %2").arg(modelData.code).arg(modelData.message)
                        wrapMode: Text.WordWrap
                        elide: Text.ElideRight
                        color: "#a45528"
                        Accessible.name: text
                    }
                }
            }

            Label { text: qsTr("Windings"); font.bold: true; color: "#1e2b32" }

            // Fixed-width column headers: same idiom as the table rows
            // below them. `Layout.minimumWidth: 0` lets each column shrink
            // (rather than force the whole panel wider) when the panel is
            // narrower than the sum of every column's preferred width --
            // Qt Quick Layouts otherwise defaults a Label's minimum width to
            // its own (unshrinkable) implicit text width.
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Label { Layout.fillWidth: true; Layout.preferredWidth: 70; text: qsTr("Winding"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; Layout.preferredWidth: 110; text: qsTr("Copper area"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; Layout.preferredWidth: 110; text: qsTr("Wire length"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; Layout.preferredWidth: 110; text: qsTr("Resistance"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; Layout.preferredWidth: 110; text: qsTr("J AC RMS"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; Layout.preferredWidth: 110; text: qsTr("J AC peak"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; Layout.preferredWidth: 110; text: qsTr("J DC"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.fillWidth: true; text: qsTr("Wire loss"); elide: Text.ElideRight; color: "#6d7a7e" }
            }

            ListView {
                id: windingTable
                objectName: "preliminaryWindingTable"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, count * 64)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.windingRows : []
                Accessible.name: qsTr("Per-winding preliminary results")

                delegate: ColumnLayout {
                    required property var modelData
                    width: ListView.view.width
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Label { Layout.preferredWidth: 70; Layout.minimumWidth: 0; text: modelData.windingId; elide: Text.ElideRight; font.bold: true }
                        Label {
                            Layout.preferredWidth: 110
                            Layout.minimumWidth: 0
                            text: modelData.conductorArea.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.conductorArea.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            Layout.minimumWidth: 0
                            text: modelData.wireLength.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.wireLength.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            Layout.minimumWidth: 0
                            text: modelData.resistance.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.resistance.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            Layout.minimumWidth: 0
                            text: modelData.jAcRms.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.jAcRms.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            Layout.minimumWidth: 0
                            text: modelData.jAcPeak.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.jAcPeak.state)
                        }
                        Label {
                            Layout.preferredWidth: 110
                            Layout.minimumWidth: 0
                            text: modelData.jDc.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.jDc.state)
                        }
                        Label {
                            Layout.fillWidth: true
                            text: modelData.wireLoss.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.wireLoss.state)
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: modelData.wireLoss.message !== "" || modelData.jAcRms.message !== ""
                        text: modelData.wireLoss.message !== ""
                            ? qsTr("%1 — %2").arg(modelData.wireLoss.code).arg(modelData.wireLoss.message)
                            : qsTr("%1 — %2").arg(modelData.jAcRms.code).arg(modelData.jAcRms.message)
                        wrapMode: Text.WordWrap
                        color: "#a45528"
                        font.pixelSize: 11
                        Accessible.name: text
                    }
                }
            }

            Label { text: qsTr("Totals"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: totalsTable
                objectName: "preliminaryTotalsTable"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(40, count * 40)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.totalRows : []
                Accessible.name: qsTr("Preliminary loss totals")

                delegate: RowLayout {
                    required property var modelData
                    width: ListView.view.width
                    height: 40
                    spacing: 8
                    Label { Layout.preferredWidth: 220; Layout.minimumWidth: 0; text: modelData.label; elide: Text.ElideRight; color: "#6d7a7e" }
                    Label {
                        Layout.preferredWidth: 140
                        Layout.minimumWidth: 0
                        text: modelData.text
                        elide: Text.ElideRight
                        font.bold: true
                        color: preliminaryPage.stateColor(modelData.state)
                    }
                    Label {
                        Layout.fillWidth: true
                        text: modelData.code === "" ? "" : qsTr("%1 — %2").arg(modelData.code).arg(modelData.message)
                        wrapMode: Text.WordWrap
                        color: "#a45528"
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                color: "#fff4ec"
                radius: 6
                visible: geometryIssues.count > 0
                implicitHeight: geometryIssues.contentHeight + 20

                ListView {
                    id: geometryIssues
                    objectName: "preliminaryGeometryIssues"
                    anchors.fill: parent
                    anchors.margins: 10
                    interactive: false
                    model: preliminaryPage.controller !== null ? preliminaryPage.controller.geometryIssues : []
                    Accessible.name: qsTr("Geometry issues")
                    delegate: Label {
                        required property string modelData
                        width: ListView.view.width
                        text: qsTr("Geometry: %1").arg(modelData)
                        wrapMode: Text.WordWrap
                        color: "#a45528"
                    }
                }
            }

            Label { text: qsTr("Assumptions and excluded effects"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: assumptions
                objectName: "preliminaryAssumptions"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(24, contentHeight)
                interactive: false
                model: preliminaryPage.controller !== null ? preliminaryPage.controller.assumptions : []
                Accessible.name: qsTr("Preliminary assumptions")
                delegate: Label {
                    required property string modelData
                    width: ListView.view.width
                    text: qsTr("• %1").arg(modelData)
                    wrapMode: Text.WordWrap
                    color: "#6d7a7e"
                }
            }
        }
    }
}
