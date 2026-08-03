from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtQml import QQmlApplicationEngine

    from inductor_designer.domain.project import InductorProject
    from inductor_designer.ui.core_material_controller import CoreMaterialController
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.guided_studio_controller import GuidedStudioController
    from inductor_designer.ui.material_studio_controller import MaterialStudioController
    from inductor_designer.ui.preliminary_controller import PreliminaryController
    from inductor_designer.ui.preview_geometry import PreviewEntry
    from inductor_designer.ui.project_session import ProjectSession
    from inductor_designer.ui.review_controller import ReviewController
    from inductor_designer.ui.simulation_controller import SimulationController

_DEFAULT_CATALOG = Path("artifacts/catalog/catalog.sqlite")
_DEFAULT_SCHEMAS = Path("schemas")
_DEFAULT_MATRIX = Path("compatibility/aedt-matrix.yml")
_DEFAULT_MATERIAL_OVERLAY = Path("materials-overlay")


def qml_directory() -> Path:
    return Path(__file__).with_name("qml")


def create_engine(
    preview_entries: list[PreviewEntry] | None = None,
    simulation_summary: list[str] | None = None,
    generation_controller: GenerationController | None = None,
    backend_choices: list[str] | None = None,
    material_studio_controller: MaterialStudioController | None = None,
    guided_studio_controller: GuidedStudioController | None = None,
    project_session: ProjectSession | None = None,
    core_material_controller: CoreMaterialController | None = None,
    preliminary_controller: PreliminaryController | None = None,
    simulation_controller: SimulationController | None = None,
    review_controller: ReviewController | None = None,
) -> QQmlApplicationEngine:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    if preview_entries is not None:
        engine.rootContext().setContextProperty("previewEntries", preview_entries)
    engine.rootContext().setContextProperty("guidedStudioController", guided_studio_controller)
    engine.rootContext().setContextProperty("simulationSummary", simulation_summary or [])
    engine.rootContext().setContextProperty("generationController", generation_controller)
    engine.rootContext().setContextProperty("backendChoices", backend_choices or [])
    engine.rootContext().setContextProperty(
        "materialStudioController", material_studio_controller
    )
    engine.rootContext().setContextProperty("projectSession", project_session)
    engine.rootContext().setContextProperty("coreMaterialController", core_material_controller)
    engine.rootContext().setContextProperty("preliminaryController", preliminary_controller)
    engine.rootContext().setContextProperty("simulationController", simulation_controller)
    engine.rootContext().setContextProperty("reviewController", review_controller)
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


def _load_simulation_summary(project: InductorProject) -> list[str]:
    from inductor_designer.application.services.simulation_summary import simulation_summary

    return list(simulation_summary(project))


def _build_generation_controller(
    session: ProjectSession,
    catalog_path: Path,
    matrix_path: Path,
    project_document_path: Path,
) -> GenerationController:
    from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
    from inductor_designer.adapters.compatibility.matrix_repository import (
        MatrixCapabilityRepository,
    )
    from inductor_designer.adapters.femm.solver import PyfemmSolver
    from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
    from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
    from inductor_designer.application.services.aedt_support import (
        SUPPORTED_AEDT_EDITION,
        SUPPORTED_AEDT_RELEASE,
    )
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.generation_lines import (
        GenerationBackend,
        GenerationResult,
        run_generation,
    )

    catalog = SqliteCatalogRepository(catalog_path)
    matrix = MatrixCapabilityRepository(matrix_path)
    maxwell3d_exporter = PyaedtMaxwell3dExporter()
    maxwell2d_exporter = PyaedtMaxwell2dExporter()
    femm_solver = PyfemmSolver()

    def runner(backend_label: str, show_solver_window: bool) -> GenerationResult:
        project = session.project
        capabilities = matrix.snapshot_for(
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION,
        )
        backend = GenerationBackend(backend_label)
        return run_generation(
            backend,
            project,
            project_document_path,
            catalog,
            capabilities,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            show_solver_window=show_solver_window,
        )

    return GenerationController(runner)


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
    generation_controller: GenerationController | None = None
    backend_choices: list[str] = []
    project: InductorProject | None = None
    if args.project is not None:
        from inductor_designer.application.services.geometry_model import GeometryModelError
        from inductor_designer.ui.generation_lines import GenerationBackend

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
            simulation_summary = _load_simulation_summary(project)
        except GeometryModelError as error:
            for issue in error.issues:
                print(issue, file=sys.stderr)
            return 3
        backend_choices = [backend.value for backend in GenerationBackend]
        print(
            f"Loaded {args.project.name}: {len(preview_entries) - 1} winding(s); opening viewer.",
            file=sys.stderr,
            flush=True,
        )

    from inductor_designer.adapters.materials import FileOverlayMaterialRepository
    from inductor_designer.ui.material_studio_controller import MaterialStudioController

    project_save_callback: Callable[[InductorProject], None] | None = None
    if project is not None and args.project is not None:
        from inductor_designer.adapters.persistence.project_repository import (
            ProjectRepository,
        )
        from inductor_designer.adapters.persistence.schema_repository import (
            SchemaRepository,
        )

        project_repository = ProjectRepository(SchemaRepository(_DEFAULT_SCHEMAS))

        def save_project(updated_project: InductorProject) -> None:
            project_repository.save(updated_project, args.project)

        project_save_callback = save_project

    session: ProjectSession | None = None
    if project is not None:
        from inductor_designer.ui.project_session import ProjectSession

        session = ProjectSession(project, args.project, project_save_callback)
        generation_controller = _build_generation_controller(
            session, args.catalog, args.matrix, args.project
        )

    material_repository = FileOverlayMaterialRepository(_DEFAULT_MATERIAL_OVERLAY)
    material_studio_controller = MaterialStudioController(
        material_repository,
        pinned_revision=(
            lambda: session.project.design.core_material if session is not None else None
        ),
    )

    from inductor_designer.adapters.system.path_opener import DesktopPathOpener
    from inductor_designer.application.services.aedt_support import (
        SUPPORTED_AEDT_EDITION,
        SUPPORTED_AEDT_RELEASE,
    )
    from inductor_designer.ui.core_material_controller import CoreMaterialController
    from inductor_designer.ui.preliminary_controller import PreliminaryController
    from inductor_designer.ui.review_controller import ReviewController
    from inductor_designer.ui.simulation_controller import SimulationController

    guided_studio_controller: GuidedStudioController | None = None
    core_material_controller: CoreMaterialController | None = None
    preliminary_controller: PreliminaryController | None = None
    simulation_controller: SimulationController | None = None
    review_controller: ReviewController | None = None
    if session is not None and generation_controller is not None:
        from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
        from inductor_designer.adapters.compatibility.matrix_repository import (
            MatrixCapabilityRepository,
        )
        from inductor_designer.ui.guided_studio_controller import GuidedStudioController

        # One catalog reader and one material overlay reader, shared by every
        # screen: a material imported in the Material Studio window (which
        # shares `material_repository` above) is visible to the Core &
        # Material selector without a process restart.
        catalog_repository = SqliteCatalogRepository(args.catalog)
        capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
            SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION
        )
        guided_studio_controller = GuidedStudioController(session, catalog_repository)
        core_material_controller = CoreMaterialController(
            session, catalog_repository, material_repository
        )
        preliminary_controller = PreliminaryController(session, catalog_repository)
        simulation_controller = SimulationController(
            session, generation_controller, capabilities
        )
        review_controller = ReviewController(
            session,
            preliminary_controller,
            generation_controller,
            catalog_repository,
            DesktopPathOpener(),
        )
        # One project, one recompute path: every edit lands on the session,
        # and the dependent screens refresh from it. ReviewController already
        # connects session.projectChanged to its own refresh in its
        # constructor, so it is deliberately not connected again here.
        session.projectChanged.connect(preliminary_controller.refresh)
        session.projectChanged.connect(guided_studio_controller.refresh)

    engine = create_engine(
        preview_entries,
        simulation_summary,
        generation_controller,
        backend_choices,
        material_studio_controller,
        guided_studio_controller,
        session,
        core_material_controller,
        preliminary_controller,
        simulation_controller,
        review_controller,
    )
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
