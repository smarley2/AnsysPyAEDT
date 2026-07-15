import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

Rectangle {
    color: "#111827"

    property bool hasPreviewEntries: typeof previewEntries !== "undefined"

    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            clearColor: hasPreviewEntries ? "#1a1a2e" : "#111827"
            backgroundMode: SceneEnvironment.Color
        }

        PerspectiveCamera {
            id: camera
            // Project view: 3/4 view aimed at the origin (forward = -Z rotated
            // +45 deg about X exactly hits (0,0,0) from (0,-60,60)).
            position: hasPreviewEntries ? Qt.vector3d(0, -60, 60) : Qt.vector3d(0, 0, 450)
            eulerRotation.x: hasPreviewEntries ? 45 : 0
        }
        OrbitCameraController { camera: camera; origin: originNode }
        Node { id: originNode }
        DirectionalLight { eulerRotation.x: -30 }
        DirectionalLight { eulerRotation.x: 150; brightness: 0.5 }

        // Foundation preview spike: shown until a real project supplies previewEntries.
        Model {
            visible: !hasPreviewEntries
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
            visible: !hasPreviewEntries
            source: "#Cylinder"
            x: 120
            scale: Qt.vector3d(0.12, 1.1, 0.12)
            eulerRotation.x: 68
            materials: PrincipledMaterial { baseColor: "#d97706" }
        }

        Repeater3D {
            model: hasPreviewEntries ? previewEntries : []
            Model {
                geometry: modelData.geometry
                scale: Qt.vector3d(1000, 1000, 1000) // meters -> millimeters for camera sanity
                materials: DefaultMaterial {
                    diffuseColor: modelData.color
                    opacity: modelData.opacity
                }
            }
        }
    }
}
