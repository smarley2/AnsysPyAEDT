from __future__ import annotations

import argparse
import contextlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtQml import QQmlApplicationEngine

    from inductor_designer.domain.project import InductorProject
    from inductor_designer.ui.app_info_controller import AppInfoController
    from inductor_designer.ui.core_material_controller import CoreMaterialController
    from inductor_designer.ui.diagnostics_controller import DiagnosticsController
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.guided_studio_controller import GuidedStudioController
    from inductor_designer.ui.material_studio_controller import MaterialStudioController
    from inductor_designer.ui.preliminary_controller import PreliminaryController
    from inductor_designer.ui.preview_geometry import PreviewEntry
    from inductor_designer.ui.project_session import ProjectSession
    from inductor_designer.ui.recovery_controller import RecoveryController
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
    app_info_controller: AppInfoController | None = None,
    recovery_controller: RecoveryController | None = None,
    diagnostics_controller: DiagnosticsController | None = None,
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
    engine.rootContext().setContextProperty("appInfo", app_info_controller)
    engine.rootContext().setContextProperty("recoveryController", recovery_controller)
    engine.rootContext().setContextProperty("diagnosticsController", diagnostics_controller)
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
        UiRunRequest,
        run_generation,
    )

    catalog = SqliteCatalogRepository(catalog_path)
    matrix = MatrixCapabilityRepository(matrix_path)
    maxwell3d_exporter = PyaedtMaxwell3dExporter()
    maxwell2d_exporter = PyaedtMaxwell2dExporter()
    femm_solver = PyfemmSolver()

    def runner(request: UiRunRequest) -> GenerationResult:
        project = session.project
        # Read the path live rather than capturing it at construction: Open
        # and Save As can move it after this controller was built, and
        # `SimulationController`'s run gate already refuses to call here at
        # all while it is unset.
        document_path = session.document_path
        if document_path is None:
            raise RuntimeError("The project has no document path to generate into.")
        capabilities = matrix.snapshot_for(
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION,
        )
        backend = GenerationBackend(request.backend_label)
        return run_generation(
            backend,
            project,
            document_path,
            catalog,
            capabilities,
            maxwell3d_exporter=maxwell3d_exporter,
            maxwell2d_exporter=maxwell2d_exporter,
            femm_solver=femm_solver,
            show_solver_window=request.show_solver_window,
            solve=request.solve,
            progress=request.progress,
            cancellation=request.cancellation,
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

    from inductor_designer import __version__
    from inductor_designer.adapters.system.app_logging import (
        LOGGER_NAME,
        configure_application_logging,
    )
    from inductor_designer.adapters.system.environment import (
        environment_redaction_context,
        log_directory,
    )

    redaction_context = environment_redaction_context()
    app_log_path = configure_application_logging(log_directory(), redaction_context)
    logger = logging.getLogger(LOGGER_NAME)
    logger.info("Application %s starting.", __version__)

    args = _parse_args(sys.argv[1:])
    _install_qml_logging()
    app = QGuiApplication(sys.argv)

    preview_entries: list[PreviewEntry] | None = None
    simulation_summary: list[str] = []
    generation_controller: GenerationController | None = None
    recovery_controller: RecoveryController | None = None
    diagnostics_controller: DiagnosticsController | None = None
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

    session: ProjectSession | None = None
    if project is not None:
        from inductor_designer.adapters.persistence.project_repository import (
            ProjectRepository,
        )
        from inductor_designer.adapters.persistence.recovery_store import RecoveryStore
        from inductor_designer.adapters.persistence.schema_repository import (
            SchemaRepository,
        )
        from inductor_designer.adapters.system.environment import recovery_directory
        from inductor_designer.ui.diagnostics_controller import DiagnosticsController
        from inductor_designer.ui.project_session import ProjectSession
        from inductor_designer.ui.recovery_controller import RecoveryController

        project_repository = ProjectRepository(SchemaRepository(_DEFAULT_SCHEMAS))
        recovery_store = RecoveryStore(recovery_directory(), project_repository)

        def autosave_project(
            updated_project: InductorProject, document_path: Path | None
        ) -> None:
            recovery_store.write(updated_project, document_path)

        def clear_recovery_snapshot() -> None:
            # Reads the session's *current* document path, same reasoning as
            # `save_project` below: Open and Save As can move it after
            # startup, and clearing must always target the slot the session
            # is actually in, never the one it started at. `session` is
            # assigned right after this closure is built, not before, but
            # only ever called later -- by which time it is bound.
            assert session is not None
            recovery_store.clear(session.document_path)

        session = ProjectSession(
            project,
            args.project,
            open_callback=_load_project,
            autosave_callback=autosave_project,
            recovery_cleanup=clear_recovery_snapshot,
        )

        def save_project(updated_project: InductorProject) -> None:
            # Reads the session's *current* document path, not `args.project`:
            # Open and Save As can move it after startup, and Save must always
            # follow, never keep writing to where the app happened to start.
            document_path = session.document_path
            if document_path is None:
                raise RuntimeError("The project has no document path to save into.")
            project_repository.save(updated_project, document_path)

        session.set_save_callback(save_project)
        generation_controller = _build_generation_controller(session, args.catalog, args.matrix)
        # Open (menu item or File > Open) can run while this controller's own
        # run is in flight -- it is a daemon thread, not something Open is
        # gated on. `openProject`'s reconcile-on-open needs this to tell a
        # live run's "running" marker apart from an abandoned one.
        session.set_busy_check(lambda: bool(generation_controller.busy))

        # A run directory still reading "running" at startup means its process
        # died mid-run. Reconcile it to "interrupted" so Review never reads it
        # as a result; a failure here must never block opening the app, since
        # the project itself is unaffected. Safe unconditionally here: nothing
        # can be busy before any run has started.
        from inductor_designer.application.services.run_recovery import (
            reconcile_unfinished_runs,
        )

        with contextlib.suppress(OSError):
            reconcile_unfinished_runs(args.project)

        # Assigned to a name, not passed inline, for the same reason as
        # `app_info_controller` below: a parent-less QObject with no
        # surviving Python reference is garbage collected out from under
        # `setContextProperty`, and this function's own stack frame is what
        # keeps it alive for the life of the app.
        recovery_controller = RecoveryController(recovery_store, session)
        diagnostics_controller = DiagnosticsController(
            session, app_log_path, redaction_context
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
        session.projectChanged.connect(core_material_controller.refresh)

    from inductor_designer.ui.app_info_controller import AppInfoController

    # Assigned to a name, not passed inline: a QObject with no Qt-parent and
    # no surviving Python reference is garbage collected out from under
    # `setContextProperty`, and `main()`'s own stack frame (alive until
    # `app.exec()` returns) is what keeps this one alive.
    app_info_controller = AppInfoController()
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
        app_info_controller,
        recovery_controller,
        diagnostics_controller,
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
