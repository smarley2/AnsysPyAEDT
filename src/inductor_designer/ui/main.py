from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtQml import QQmlApplicationEngine

    from inductor_designer.domain.project import InductorProject
    from inductor_designer.ui.preview_geometry import PreviewEntry

_DEFAULT_CATALOG = Path("artifacts/catalog/catalog.sqlite")
_DEFAULT_SCHEMAS = Path("schemas")
_DEFAULT_MATRIX = Path("compatibility/aedt-matrix.yml")


def qml_directory() -> Path:
    return Path(__file__).with_name("qml")


def create_engine(
    preview_entries: list[PreviewEntry] | None = None,
    simulation_summary: list[str] | None = None,
) -> QQmlApplicationEngine:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    if preview_entries is not None:
        engine.rootContext().setContextProperty("previewEntries", preview_entries)
    engine.rootContext().setContextProperty("simulationSummary", simulation_summary or [])
    engine.load(QUrl.fromLocalFile(str(qml_directory() / "Main.qml")))
    return engine


def _load_project(project_path: Path) -> InductorProject:
    from inductor_designer.adapters.persistence.project_repository import ProjectRepository
    from inductor_designer.adapters.persistence.schema_repository import SchemaRepository

    repo = ProjectRepository(SchemaRepository(_DEFAULT_SCHEMAS))
    return repo.load(project_path)


def _load_preview_entries(project: InductorProject, catalog_path: Path) -> list[PreviewEntry]:
    from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
    from inductor_designer.application.services.geometry_model import build_geometry_model
    from inductor_designer.ui.preview_geometry import build_preview_entries

    catalog = SqliteCatalogRepository(catalog_path)
    model = build_geometry_model(project, catalog)
    return build_preview_entries(model)


def _load_simulation_summary(project: InductorProject, matrix_path: Path) -> list[str]:
    from inductor_designer.adapters.compatibility.matrix_repository import (
        MatrixCapabilityRepository,
    )
    from inductor_designer.application.services.simulation_summary import simulation_summary

    capabilities = MatrixCapabilityRepository(matrix_path).snapshot_for(
        project.target_release, project.target_edition
    )
    return list(simulation_summary(project, capabilities))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="inductor-designer")
    parser.add_argument("--project", type=Path, default=None)
    parser.add_argument("--catalog", type=Path, default=_DEFAULT_CATALOG)
    parser.add_argument("--matrix", type=Path, default=_DEFAULT_MATRIX)
    return parser.parse_args(argv)


def _install_qml_logging() -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def handler(mode: QtMsgType, context: object, message: str) -> None:
        print(f"[qml] {message}", file=sys.stderr, flush=True)

    qInstallMessageHandler(handler)


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    args = _parse_args(sys.argv[1:])
    _install_qml_logging()
    app = QGuiApplication(sys.argv)

    preview_entries: list[PreviewEntry] | None = None
    simulation_summary: list[str] = []
    if args.project is not None:
        from inductor_designer.application.services.geometry_model import GeometryModelError

        if not args.project.is_file():
            print(f"Project file not found: {args.project}", file=sys.stderr)
            return 4
        if not args.catalog.is_file():
            print("Catalog index not found; run: python -m tools.build_catalog", file=sys.stderr)
            return 2
        if not args.matrix.is_file():
            print(f"Compatibility matrix not found: {args.matrix}", file=sys.stderr)
            return 2
        try:
            project = _load_project(args.project)
            preview_entries = _load_preview_entries(project, args.catalog)
            simulation_summary = _load_simulation_summary(project, args.matrix)
        except GeometryModelError as error:
            for issue in error.issues:
                print(issue, file=sys.stderr)
            return 3
        print(
            f"Loaded {args.project.name}: {len(preview_entries) - 1} winding(s); opening viewer.",
            file=sys.stderr,
            flush=True,
        )

    engine = create_engine(preview_entries, simulation_summary)
    roots = engine.rootObjects()
    if not roots:
        print("QML failed to load; no window created.", file=sys.stderr, flush=True)
        return 1
    # Raise the window to the front so it is not lost behind the terminal.
    window = roots[0]
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "requestActivate"):
        window.requestActivate()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
