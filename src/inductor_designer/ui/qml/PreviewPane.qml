import QtQuick
import QtQuick3D

Rectangle {
    color: "#111827"

    View3D {
        anchors.fill: parent
        environment: SceneEnvironment {
            clearColor: "#111827"
            backgroundMode: SceneEnvironment.Color
        }

        PerspectiveCamera { z: 450 }
        DirectionalLight { eulerRotation.x: -35; eulerRotation.y: -30 }
        Model {
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
            source: "#Cylinder"
            x: 120
            scale: Qt.vector3d(0.12, 1.1, 0.12)
            eulerRotation.x: 68
            materials: PrincipledMaterial { baseColor: "#d97706" }
        }
    }
}
