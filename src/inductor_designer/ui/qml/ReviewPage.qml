import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: reviewPage
    objectName: "reviewPage"
    property var controller: null

    ScrollView {
        anchors.fill: parent
        clip: true
        contentWidth: availableWidth

        ColumnLayout {
            width: reviewPage.width - 24
            spacing: 12

            Label {
                text: qsTr("Design / Review")
                font.pixelSize: 11
                font.letterSpacing: 1.2
                color: "#6d7a7e"
            }
            Label {
                text: qsTr("Review before generation")
                font.pixelSize: 24
                font.bold: true
                color: "#1e2b32"
            }
            Label {
                Layout.fillWidth: true
                text: qsTr("The generated solver project is an independent output. Edits made inside Maxwell or FEMM are never imported back into the project document.")
                wrapMode: Text.WordWrap
                color: "#6d7a7e"
            }

            ListView {
                id: sections
                objectName: "reviewSections"
                Layout.fillWidth: true
                Layout.preferredHeight: contentHeight
                interactive: false
                model: reviewPage.controller !== null ? reviewPage.controller.sections : []
                Accessible.name: qsTr("Review sections")

                delegate: ColumnLayout {
                    required property var modelData
                    width: ListView.view.width
                    spacing: 4

                    Label {
                        text: modelData.title
                        font.bold: true
                        color: "#1e2b32"
                        Accessible.name: text
                    }
                    Repeater {
                        model: modelData.rows
                        delegate: RowLayout {
                            required property var modelData
                            width: parent.width
                            spacing: 8
                            Label {
                                Layout.preferredWidth: 240
                                text: modelData.label
                                color: "#6d7a7e"
                                wrapMode: Text.WordWrap
                            }
                            Label {
                                Layout.fillWidth: true
                                text: modelData.text
                                color: "#1e2b32"
                                wrapMode: Text.WordWrap
                                Accessible.name: qsTr("%1: %2").arg(modelData.label).arg(modelData.text)
                            }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: "#d8d4cd" }
                }
            }

            Label { text: qsTr("Validation findings"); font.bold: true; color: "#1e2b32" }

            ListView {
                id: findings
                objectName: "reviewFindings"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(24, contentHeight)
                interactive: false
                model: reviewPage.controller !== null ? reviewPage.controller.findings : []
                Accessible.name: qsTr("Validation findings")
                delegate: Label {
                    required property var modelData
                    width: ListView.view.width
                    text: qsTr("%1 · %2 — %3")
                        .arg(modelData.category)
                        .arg(modelData.code)
                        .arg(modelData.message)
                    wrapMode: Text.WordWrap
                    color: modelData.category === "error" ? "#a4282d" : "#6d7a7e"
                    Accessible.name: text
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Button {
                    objectName: "openGeneratedFileButton"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    text: qsTr("Open generated file")
                    enabled: reviewPage.controller !== null && reviewPage.controller.canOpenGeneratedFile
                    Accessible.name: qsTr("Open the generated solver project")
                    onClicked: reviewPage.controller.openGeneratedFile()
                }
                Button {
                    objectName: "openRunFolderButton"
                    Layout.fillWidth: true
                    activeFocusOnTab: true
                    text: qsTr("Open run folder")
                    enabled: reviewPage.controller !== null && reviewPage.controller.canOpenRunFolder
                    Accessible.name: qsTr("Open the run folder")
                    onClicked: reviewPage.controller.openRunFolder()
                }
            }

            Label {
                objectName: "reviewMessage"
                Layout.fillWidth: true
                text: reviewPage.controller === null ? "" : reviewPage.controller.message
                wrapMode: Text.WordWrap
                color: "#a45528"
                Accessible.name: text
            }
        }
    }
}
