from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtQml import QQmlApplicationEngine


def qml_directory() -> Path:
    return Path(__file__).with_name("qml")


def create_engine() -> QQmlApplicationEngine:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile(str(qml_directory() / "Main.qml")))
    return engine


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication(sys.argv)
    engine = create_engine()
    if not engine.rootObjects():
        return 1
    return app.exec()
