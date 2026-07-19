import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Page {
    id: materialStudioPage
    property var controller: null

    padding: 16

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        Label {
            text: qsTr("Material Studio")
            font.pixelSize: 24
            font.bold: true
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            MaterialLibraryPane {
                objectName: "materialLibraryPane"
                Layout.preferredWidth: 430
                Layout.fillHeight: true
                controller: materialStudioPage.controller
            }

            MaterialValidationPane {
                Layout.fillWidth: true
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
