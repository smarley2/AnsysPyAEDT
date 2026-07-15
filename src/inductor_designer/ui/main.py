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

        if not args.project.is_file():
            print(f"Project file not found: {args.project}", file=sys.stderr)
            return 4
        if not args.catalog.is_file():
            print("Catalog index not found; run: python -m tools.build_catalog", file=sys.stderr)
            return 2
        try:
            preview_entries = _load_preview_entries(args.project, args.catalog)
        except GeometryModelError as error:
            for issue in error.issues:
                print(issue, file=sys.stderr)
            return 3
        print(
            f"Loaded {args.project.name}: {len(preview_entries) - 1} winding(s); opening viewer.",
            file=sys.stderr,
        )

    engine = create_engine(preview_entries)
    roots = engine.rootObjects()
    if not roots:
        print("QML failed to load; no window created.", file=sys.stderr)
        return 1
    # Raise the window to the front so it is not lost behind the terminal.
    window = roots[0]
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "requestActivate"):
        window.requestActivate()
    return int(app.exec())
