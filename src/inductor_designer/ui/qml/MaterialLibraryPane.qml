import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Pane {
    id: materialLibraryPane
    property var controller: null
    property alias materialListView: materialList

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
            text: qsTr("Material library")
            font.bold: true
        }

        ListView {
            id: materialList
            objectName: "materialList"
            Layout.fillWidth: true
            Layout.fillHeight: true
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
    }
}
