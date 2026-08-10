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
        id: preliminaryScrollView
        objectName: "preliminaryScrollView"
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth
        // Reserve the vertical scrollbar's own fixed width unconditionally
        // instead of binding to `availableWidth`: `availableWidth` reserves
        // for the scrollbar based on content height, which here depends on
        // this column's own width (wrapping `Label`s) -- see
        // `WindingPanel.qml` for the feedback-loop staleness this avoids.
        property real scrollBarReserve: ScrollBar.vertical ? ScrollBar.vertical.width : 0

        ColumnLayout {
            width: preliminaryScrollView.width - preliminaryScrollView.leftPadding
                - preliminaryScrollView.scrollBarReserve
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
            // below them. None of the nine columns has `Layout.fillWidth`
            // -- each is pinned at its own `Layout.preferredWidth` so the
            // table's columns never scale with the window (Fabio: "it is
            // moving the width according to the width of the screen"). The
            // `RowLayout` itself still gets `Layout.fillWidth: true` so it
            // spans the available row width, but with no fillWidth child to
            // stretch into that space, any leftover space simply sits empty
            // to the right of the last column instead of widening the
            // columns -- the table stays left-aligned. At a window narrower
            // than the sum of the nine preferred widths, elide still keeps
            // each column's own text from forcing the row wider.
            //
            // The widths themselves are budgeted, not chosen freely: the
            // ninth column (Inductance) pushed the row to 1014px, past the
            // 927px available inside the scroll view at the narrowest
            // supported window, which `test_panel_layout_containment` fails
            // on. 56 + 8 * 100 + 8 * 8 spacing = 920px fits. Widening any
            // column, or adding a tenth, needs the same sum re-checked.
            RowLayout {
                objectName: "preliminaryWindingTableHeader"
                Layout.fillWidth: true
                spacing: 8
                Label { Layout.preferredWidth: 56; text: qsTr("Winding"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("Copper area"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("Wire length"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("Resistance"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("J AC RMS"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("J AC peak"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("J DC"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("Wire loss"); elide: Text.ElideRight; color: "#6d7a7e" }
                Label { Layout.preferredWidth: 100; text: qsTr("Inductance"); elide: Text.ElideRight; color: "#6d7a7e" }
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
                        Label { Layout.preferredWidth: 56; text: modelData.windingId; elide: Text.ElideRight; font.bold: true }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.conductorArea.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.conductorArea.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.wireLength.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.wireLength.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.resistance.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.resistance.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.jAcRms.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.jAcRms.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.jAcPeak.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.jAcPeak.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.jDc.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.jDc.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.wireLoss.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.wireLoss.state)
                        }
                        Label {
                            Layout.preferredWidth: 100
                            text: modelData.inductance.text
                            elide: Text.ElideRight
                            color: preliminaryPage.stateColor(modelData.inductance.state)
                        }
                    }
                    // Inductance is checked here as well as wire loss and
                    // current density: it can be refused on its own (the core
                    // failed while the copper resolved), and without this the
                    // row would read Unavailable with no reason beside it.
                    Label {
                        Layout.fillWidth: true
                        visible: modelData.wireLoss.message !== "" || modelData.jAcRms.message !== ""
                            || modelData.inductance.message !== ""
                        text: modelData.wireLoss.message !== ""
                            ? qsTr("%1 — %2").arg(modelData.wireLoss.code).arg(modelData.wireLoss.message)
                            : modelData.jAcRms.message !== ""
                            ? qsTr("%1 — %2").arg(modelData.jAcRms.code).arg(modelData.jAcRms.message)
                            : qsTr("%1 — %2").arg(modelData.inductance.code).arg(modelData.inductance.message)
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
