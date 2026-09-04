import QtQuick
import QtQuick.Controls
import QtQuick3D
import QtQuick3D.Helpers

Rectangle {
    id: pane
    objectName: "previewPane"
    color: "#f8f7f4"

    property var previewModel: guidedStudioController !== null
        ? guidedStudioController.previewEntries
        : (typeof previewEntries !== "undefined" ? previewEntries : [])
    property bool hasPreviewEntries: previewModel.length > 0
    // Read off the button rather than assigned by its `onClicked`: a click
    // toggles `checked` imperatively, so a `checked: pane.showTwoD` binding
    // would be destroyed by the first click and stop tracking afterwards.
    property bool showTwoD: previewMode2DButton.checked
    property var cutPlaneDrawing: guidedStudioController !== null
        ? guidedStudioController.cutPlaneDrawing
        : ({ "outline": [], "depth_mm": 0.0,
             "extent_mm": 1.0, "circles": [], "note": "" })

    View3D {
        anchors.fill: parent
        visible: !pane.showTwoD
        environment: SceneEnvironment {
            clearColor: pane.hasPreviewEntries ? "#f8f7f4" : "#eef0f2"
            backgroundMode: SceneEnvironment.Color
        }

        PerspectiveCamera {
            id: camera
            // Project view: 3/4 view aimed at the origin (forward = -Z rotated
            // +45 deg about X exactly hits (0,0,0) from (0,-60,60)).
            position: pane.hasPreviewEntries ? Qt.vector3d(0, -60, 60) : Qt.vector3d(0, 0, 450)
            eulerRotation.x: pane.hasPreviewEntries ? 45 : 0
        }
        OrbitCameraController { camera: camera; origin: originNode }
        Node { id: originNode }
        DirectionalLight { eulerRotation.x: -30 }
        DirectionalLight { eulerRotation.x: 150; brightness: 0.5 }

        // Foundation preview spike: shown until a real project supplies previewEntries.
        Model {
            visible: !pane.hasPreviewEntries
            source: "#Cylinder"
            scale: Qt.vector3d(1.8, 0.45, 1.8)
            eulerRotation.x: 68
            materials: PrincipledMaterial {
                baseColor: "#334155"
                metalness: 0.1
                roughness: 0.65
            }
        }
        Model {
            visible: !pane.hasPreviewEntries
            source: "#Cylinder"
            x: 120
            scale: Qt.vector3d(0.12, 1.1, 0.12)
            eulerRotation.x: 68
            materials: PrincipledMaterial { baseColor: "#d97706" }
        }

        Repeater3D {
            model: pane.previewModel
            Model {
                geometry: modelData.geometry
                scale: Qt.vector3d(1000, 1000, 1000) // meters -> millimeters for camera sanity
                materials: DefaultMaterial {
                    diffuseColor: modelData.color
                    opacity: modelData.opacity
                }
            }
        }

        // The equatorial XY plane the 2D model is cut on. The toroid axis is z,
        // so the built-in rectangle already lies in the right plane. Its native
        // size is 100 units and the scene draws metres scaled by 1000, so the
        // scale factor is the wanted size in millimetres over 100.
        // ponytail: one fixed plane, because XY equatorial is the only
        // reduction the 2D adapters build. It becomes a selector when a core
        // shape arrives whose plane is not obvious.
        Model {
            objectName: "cutPlaneModel"
            visible: showCutPlaneCheck.checked && pane.hasPreviewEntries
            source: "#Rectangle"
            scale: {
                var size = 2.2 * pane.cutPlaneDrawing.extent_mm
                return Qt.vector3d(size / 100, size / 100, 1)
            }
            materials: PrincipledMaterial {
                baseColor: "#3f88c5"
                opacity: 0.18
                alphaMode: PrincipledMaterial.Blend
                // `depthDrawMode` and `cullMode` live on `Material`, which
                // `PrincipledMaterial` derives from -- not on `Model`. The
                // translucent plane must neither occlude the core behind it
                // nor vanish when the orbit camera swings past its back.
                cullMode: Material.NoCulling
                depthDrawMode: Material.NeverDepthDraw
            }
        }
    }

    CutPlaneView {
        anchors.fill: parent
        visible: pane.showTwoD
        drawing: pane.cutPlaneDrawing
        background: pane.color
    }

    // Only the two mode buttons, never the checkbox: `CheckBox` is an
    // `AbstractButton` too, so handing the group the whole row would make
    // "Show cut plane" mutually exclusive with the mode it belongs to.
    ButtonGroup { buttons: [previewMode3DButton, previewMode2DButton] }

    // Anchored to the top right, not the top left: `Main.qml` already parks an
    // opaque "mm - real geometry" badge over the pane's top left corner.
    Row {
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 10
        spacing: 8

        Button {
            id: previewMode3DButton
            objectName: "previewMode3DButton"
            text: qsTr("3D")
            checkable: true
            checked: true
        }
        Button {
            id: previewMode2DButton
            objectName: "previewMode2DButton"
            text: qsTr("2D cut")
            checkable: true
            // Reading the 2D model is pointless without knowing where it was
            // cut, so selecting it arms the plane in the 3D scene too. It is
            // left armed on the way back, which is the point.
            onCheckedChanged: if (checked) showCutPlaneCheck.checked = true
        }
        CheckBox {
            id: showCutPlaneCheck
            objectName: "showCutPlaneCheck"
            text: qsTr("Show cut plane")
        }
    }
}
