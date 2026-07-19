import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialLibraryPane
    property var controller: null

    function statusText(status) {
        switch (status) {
        case "draft":
            return qsTr("Draft")
        case "reviewed":
            return qsTr("Reviewed")
        case "approved":
            return qsTr("Approved")
        default:
            return String(status)
        }
    }

    function revisionDescription(revision) {
        return [
            qsTr("Revision %1").arg(revision.revisionId),
            qsTr("Status: %1").arg(statusText(revision.status)),
            qsTr("Created: %1").arg(revision.createdAt),
            revision.reviewedBy
                ? qsTr("Reviewer: %1").arg(revision.reviewedBy)
                : qsTr("Reviewer: Not reviewed"),
            revision.approvedBy
                ? qsTr("Approver: %1").arg(revision.approvedBy)
                : qsTr("Approver: Not approved"),
            qsTr("Series: %1").arg(revision.seriesCount),
            qsTr("Validation errors: %1").arg(revision.validationErrors),
            qsTr("Validation warnings: %1").arg(revision.validationWarnings)
        ].join("\n")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        Label {
            text: qsTr("Library and revisions")
            font.bold: true
        }

        Label { text: qsTr("Materials") }

        ListView {
            id: materialList
            objectName: "materialList"
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(contentHeight, 104)
            clip: true
            spacing: 4
            model: materialLibraryPane.controller !== null
                ? materialLibraryPane.controller.materials
                : []
            Accessible.name: qsTr("Material library")

            delegate: Button {
                required property var modelData
                width: ListView.view.width
                height: 48
                text: qsTr("%1 — %2 — %3")
                    .arg(modelData.manufacturer)
                    .arg(modelData.name)
                    .arg(modelData.grade)
                activeFocusOnTab: true
                Accessible.name: qsTr("Select material %1, %2, %3")
                    .arg(modelData.manufacturer)
                    .arg(modelData.name)
                    .arg(modelData.grade)
                onClicked: materialLibraryPane.controller.selectMaterial(
                    modelData.manufacturer,
                    modelData.name,
                    modelData.grade
                )
                Keys.onReturnPressed: clicked()
                Keys.onEnterPressed: clicked()
            }
        }

        Label { text: qsTr("Revisions") }

        ListView {
            id: revisionList
            objectName: "revisionList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            model: materialLibraryPane.controller !== null
                ? materialLibraryPane.controller.revisions
                : []
            Accessible.name: qsTr("Material revisions")

            delegate: Frame {
                required property var modelData
                width: ListView.view.width
                height: revisionDetails.implicitHeight + 2 * padding

                ColumnLayout {
                    id: revisionDetails
                    anchors.fill: parent
                    spacing: 6

                    Label {
                        Layout.fillWidth: true
                        text: materialLibraryPane.revisionDescription(modelData)
                        wrapMode: Text.WordWrap
                        Accessible.name: text
                    }

                    Label {
                        visible: modelData.isLatestApproved
                        text: qsTr("Suggested latest approved")
                        font.bold: true
                        Accessible.name: text
                        Accessible.ignored: !visible
                    }

                    Button {
                        Layout.fillWidth: true
                        text: qsTr("Select revision %1").arg(modelData.revisionId)
                        activeFocusOnTab: true
                        Accessible.name: text
                        onClicked: materialLibraryPane.controller.selectRevision(
                            modelData.revisionId
                        )
                        Keys.onReturnPressed: clicked()
                        Keys.onEnterPressed: clicked()
                    }
                }
            }
        }
    }
}
