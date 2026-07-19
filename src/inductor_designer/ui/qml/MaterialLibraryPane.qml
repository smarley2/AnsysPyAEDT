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

    function materialText(material, isCurrent) {
        const pattern = isCurrent
            ? qsTr("Current material: %1 — %2 — %3")
            : qsTr("%1 — %2 — %3")
        return pattern
            .arg(material.manufacturer)
            .arg(material.name)
            .arg(material.grade)
    }

    function moveCurrent(view, delta) {
        if (view.count === 0) {
            view.currentIndex = -1
            return
        }
        const next = view.currentIndex < 0 ? 0 : view.currentIndex + delta
        view.currentIndex = Math.max(0, Math.min(next, view.count - 1))
        view.positionViewAtIndex(view.currentIndex, ListView.Contain)
    }

    function handleListKey(view, event) {
        switch (event.key) {
        case Qt.Key_Down:
            moveCurrent(view, 1)
            break
        case Qt.Key_Up:
            moveCurrent(view, -1)
            break
        case Qt.Key_Return:
        case Qt.Key_Enter:
        case Qt.Key_Space:
            view.activateCurrent()
            break
        default:
            return
        }
        event.accepted = true
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
            activeFocusOnTab: true
            clip: true
            currentIndex: 0
            spacing: 4
            model: materialLibraryPane.controller !== null
                ? materialLibraryPane.controller.materials
                : []
            Accessible.name: qsTr("Material library")

            Keys.onPressed: function(event) {
                materialLibraryPane.handleListKey(materialList, event)
            }

            function activateCurrent() {
                if (currentIndex < 0 || currentIndex >= count) {
                    return
                }
                const material = materialLibraryPane.controller.materials[currentIndex]
                materialLibraryPane.controller.selectMaterial(
                    material.manufacturer,
                    material.name,
                    material.grade
                )
            }

            delegate: Button {
                required property int index
                required property var modelData
                width: ListView.view.width
                height: 48
                text: materialLibraryPane.materialText(
                    modelData,
                    ListView.isCurrentItem
                )
                activeFocusOnTab: false
                focusPolicy: Qt.ClickFocus
                highlighted: ListView.isCurrentItem
                Accessible.name: qsTr("Select material %1, %2, %3")
                    .arg(modelData.manufacturer)
                    .arg(modelData.name)
                    .arg(modelData.grade)
                Accessible.description: text
                Accessible.focusable: true
                onClicked: {
                    materialList.currentIndex = index
                    materialList.positionViewAtIndex(index, ListView.Contain)
                    materialLibraryPane.controller.selectMaterial(
                        modelData.manufacturer,
                        modelData.name,
                        modelData.grade
                    )
                }
            }
        }

        Label { text: qsTr("Revisions") }

        ListView {
            id: revisionList
            objectName: "revisionList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            activeFocusOnTab: true
            clip: true
            currentIndex: 0
            spacing: 8
            model: materialLibraryPane.controller !== null
                ? materialLibraryPane.controller.revisions
                : []
            Accessible.name: qsTr("Material revisions")

            Keys.onPressed: function(event) {
                materialLibraryPane.handleListKey(revisionList, event)
            }

            function activateCurrent() {
                if (currentIndex < 0 || currentIndex >= count) {
                    return
                }
                const revision = materialLibraryPane.controller.revisions[currentIndex]
                materialLibraryPane.controller.selectRevision(revision.revisionId)
            }

            delegate: Frame {
                id: revisionRow
                required property int index
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
                        visible: revisionRow.ListView.isCurrentItem
                        text: qsTr("Current revision")
                        font.bold: true
                        Accessible.name: text
                        Accessible.ignored: !visible
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
                        activeFocusOnTab: false
                        focusPolicy: Qt.ClickFocus
                        Accessible.name: text
                        Accessible.focusable: true
                        onClicked: {
                            revisionList.currentIndex = revisionRow.index
                            revisionList.positionViewAtIndex(
                                revisionRow.index,
                                ListView.Contain
                            )
                            materialLibraryPane.controller.selectRevision(
                                modelData.revisionId
                            )
                        }
                    }
                }
            }
        }
    }
}
