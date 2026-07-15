from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtQml import QQmlApplicationEngine

    from inductor_designer.ui.preview_geometry import PreviewEntry

_DEFAULT_CATALOG = Path("artifacts/catalog/catalog.sqlite")
_DEFAULT_SCHEMAS = Path("schemas")


def qml_directory() -> Path:
    return Path(__file__).with_name("qml")


def create_engine(preview_entries: list[PreviewEntry] | None = None) -> QQmlApplicationEngine:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    if preview_entries is not None:
        engine.rootContext().setContextProperty("previewEntries", preview_entries)
    engine.load(QUrl.fromLocalFile(str(qml_directory() / "Main.qml")))
    return engine


def _load_preview_entries(project_path: Path, catalog_path: Path) -> list[PreviewEntry]:
    from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
    from inductor_designer.adapters.persistence.project_repository import ProjectRepository
    from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
    from inductor_designer.application.services.geometry_model import build_geometry_model
    from inductor_designer.ui.preview_geometry import build_preview_entries

    repo = ProjectRepository(SchemaRepository(_DEFAULT_SCHEMAS))
    project = repo.load(project_path)
    catalog = SqliteCatalogRepository(catalog_path)
    model = build_geometry_model(project, catalog)
    return build_preview_entries(model)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="inductor-designer")
    parser.add_argument("--project", type=Path, default=None)
    parser.add_argument("--catalog", type=Path, default=_DEFAULT_CATALOG)
    return parser.parse_args(argv)


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    args = _parse_args(sys.argv[1:])
    app = QGuiApplication(sys.argv)

    preview_entries: list[PreviewEntry] | None = None
    if args.project is not None:
        from inductor_designer.application.services.geometry_model import GeometryModelError

        if not args.catalog.is_file():
            print("Catalog index not found; run: python -m tools.build_catalog")
            return 2
        try:
            preview_entries = _load_preview_entries(args.project, args.catalog)
        except GeometryModelError as error:
            for issue in error.issues:
                print(issue)
            return 3

    engine = create_engine(preview_entries)
    if not engine.rootObjects():
        return 1
    return int(app.exec())
