import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1200
    height: 760
    visible: true
    title: qsTr("PyAEDT Inductor Designer")

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Frame {
            Layout.preferredWidth: 320
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                Label { text: qsTr("Core") }
                Label { text: qsTr("Windings") }
                Label { text: qsTr("Materials") }
                Label { text: qsTr("Simulation") }
                Label { text: qsTr("Review") }
                Item { Layout.fillHeight: true }
                Label { text: qsTr("Foundation preview spike") }
            }
        }

        PreviewPane {
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
