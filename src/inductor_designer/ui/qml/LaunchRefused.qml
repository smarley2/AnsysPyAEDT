import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Shown instead of the application when the project on the command line is
// already open in another window. Without it the launch printed to stderr and
// exited: from a desktop shortcut that is a click which produces no window and
// no reason, indistinguishable from a crash.
//
// Deliberately a plain Window rather than a Dialog inside the real shell: the
// shell owns a project, and at this point there is none -- the whole reason we
// are here is that the project could not be claimed.
Window {
    id: refusalWindow
    objectName: "launchRefusedWindow"
    width: 520
    height: 200
    visible: true
    title: qsTr("PyAEDT Inductor Designer")
    color: "#f3f1ed"

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        Label {
            objectName: "launchRefusedHeading"
            text: qsTr("This project is already open")
            font.pixelSize: 18
            font.bold: true
            color: "#22201d"
        }

        Label {
            objectName: "launchRefusedMessage"
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: refusalMessage
            wrapMode: Text.WordWrap
            color: "#3f3b36"
            Accessible.name: text
        }

        Button {
            objectName: "launchRefusedCloseButton"
            Layout.alignment: Qt.AlignRight
            text: qsTr("Close")
            Accessible.name: qsTr("Close this message and quit")
            onClicked: Qt.quit()
        }
    }

    onClosing: Qt.quit()
}
