from __future__ import annotations

import argparse
import contextlib
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine

    from inductor_designer.adapters.system.installations import (
        AedtInstallation,
        UnsupportedAedtInstallation,
    )
    from inductor_designer.adapters.system.project_lock import ProjectLock
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


def show_launch_refusal(message: str) -> QQmlApplicationEngine:
    """Put a refused launch on screen, and return the engine holding it.

    A refusal printed only to stderr is invisible to anyone starting the
    application from a desktop shortcut: the click produces no window and no
    reason, which reads as a crash rather than as "your other window has this
    project". The caller runs the event loop and exits; the window's Close
    button and its title-bar X both quit.

    A plain Window in its own engine, not a dialog inside the real shell: the
    shell is built around a project, and the reason we are here is that this
    project could not be claimed.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("refusalMessage", message)
    engine.load(QUrl.fromLocalFile(str(qml_directory() / "LaunchRefused.qml")))
    return engine


def _load_project(project_path: Path) -> InductorProject:
    from inductor_designer.adapters.persistence.project_repository import ProjectRepository
    from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
    from inductor_designer.adapters.system import resources

    repo = ProjectRepository(SchemaRepository(resources.schemas_directory()))
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
    from inductor_designer.adapters.system import resources

    parser = argparse.ArgumentParser(prog="inductor-designer")
    parser.add_argument("--project", type=Path, default=None)
    # The seam's defaults, not a path relative to the working directory: an
    # explicit flag here still wins, argparse only falls back to these when
    # the flag is absent.
    parser.add_argument("--catalog", type=Path, default=resources.catalog_index_path())
    parser.add_argument("--matrix", type=Path, default=resources.compatibility_matrix_path())
    # Answers known risk 2 of the M10 release record on the machine that has
    # the problem: a frozen bundle can miss a lazily imported solver module or
    # a data file PyAEDT reads off disk, and neither shows up until a run is
    # already in flight. Imports only -- no AEDT session, no license, no
    # solve, so it is safe to run anywhere the application is installed.
    parser.add_argument(
        "--check-solver-imports",
        action="store_true",
        help=(
            "Report whether this build can import the solver stack and find "
            "its data files, then exit. Does not start AEDT or solve."
        ),
    )
    return parser.parse_args(argv)


def _install_qml_logging() -> None:
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def handler(mode: QtMsgType, context: object, message: str) -> None:
        print(f"[qml] {message}", file=sys.stderr, flush=True)

    qInstallMessageHandler(handler)


def _refuse_if_resources_are_missing(
    app: QGuiApplication, logger: logging.Logger, args: argparse.Namespace
) -> int | None:
    """Refuse the launch, on both channels, if a shipped resource is absent.

    Checked before anything else is built: a shortcut launch that dies partway
    through wiring a repository is a traceback with no explanation, exactly
    the failure mode M9 ruled out for the project lock. Returns the exit code
    to use, or None when every resource resolved and startup should continue.

    ``--catalog``/``--matrix`` default to the seam's own paths, but an
    explicit flag pointing at a real file supersedes the seam's resource here
    -- someone debugging with a hand-built catalog against an otherwise
    incomplete resource root must not be refused for the very thing the flag
    fixes. A bad flag path is still caught, just further down in `main()`,
    where the per-flag checks report it against the flag, not this gate.
    """
    from inductor_designer.adapters.system import resources
    from inductor_designer.simulation.failure_advice import AdviceCode

    # name -> whether an explicit, valid flag already covers this resource.
    superseded_by_flag = {
        "catalog index": args.catalog.is_file(),
        "compatibility matrix": args.matrix.is_file(),
    }
    missing = tuple(
        item
        for item in resources.missing_resources()
        if not superseded_by_flag.get(item.name, False)
    )
    if not missing:
        return None

    lines = [f"{item.name}: not found at {item.path}" for item in missing]
    override = resources.active_override()
    if override is not None:
        # A mis-set INDUCTOR_DESIGNER_RESOURCES is the most likely cause of
        # a missing resource in a shipped build; name it so the engineer who
        # set it does not have to guess.
        lines.append(
            f"{resources.OVERRIDE_VARIABLE} is currently set to: {override}"
        )
    message = (
        f"{AdviceCode.RESOURCES_MISSING}: the application cannot find data it "
        "needs to start.\n\n" + "\n".join(lines)
    )
    print(message.replace("\n\n", " "), file=sys.stderr, flush=True)
    # Error level, and the same named list the user was shown, on one line:
    # a Start Menu launch has no console, so this log line is the only
    # durable record of which resources were missing.
    logger.error(
        "Launch refused: %d shipped resource(s) missing: %s", len(missing), "; ".join(lines)
    )
    refusal_engine = show_launch_refusal(message)
    if refusal_engine.rootObjects():
        app.exec()
    return 6


def log_detected_installations(
    logger: logging.Logger,
) -> tuple[AedtInstallation | None, UnsupportedAedtInstallation | None]:
    """Record what this machine has, and hand the findings back to the caller.

    Module level rather than inline in `main()` on purpose: `main()`'s body is
    executed by almost nothing, and this milestone has already shipped two
    defects that lived in exactly that blind spot. Here a test can drive all
    three states directly.

    "Absent" and "present but the wrong release" carry different advice codes
    because they need different remedies -- install AEDT, versus install the
    supported release beside the one you have. Both go through the redacting
    logger, since an install root is an absolute path.

    Detection never imports PyAEDT and never starts a desktop; see
    `adapters/system/installations.py`'s module docstring for why.
    """
    from inductor_designer.adapters.system.installations import (
        detect_aedt,
        detect_femm,
        detect_unsupported_aedt,
    )
    from inductor_designer.application.services.aedt_support import (
        SUPPORTED_AEDT_EDITION,
        SUPPORTED_AEDT_RELEASE,
    )
    from inductor_designer.simulation.failure_advice import AdviceCode

    aedt_installation = detect_aedt()
    unsupported_aedt_installation = detect_unsupported_aedt()
    if aedt_installation is not None:
        logger.info(
            "Detected AEDT %s at %s (via %s).",
            aedt_installation.release,
            aedt_installation.install_root,
            aedt_installation.route.value,
        )
    elif unsupported_aedt_installation is not None:
        logger.warning(
            "%s: detected AEDT %s at %s (via %s); this application supports "
            "AEDT %s %s only.",
            AdviceCode.INSTALLATION_AEDT_UNSUPPORTED_RELEASE,
            unsupported_aedt_installation.release,
            unsupported_aedt_installation.install_root,
            unsupported_aedt_installation.route.value,
            SUPPORTED_AEDT_RELEASE,
            SUPPORTED_AEDT_EDITION.value,
        )
    else:
        logger.warning(
            "%s: AEDT was not detected on this machine.",
            AdviceCode.INSTALLATION_AEDT_MISSING,
        )
    femm_installation = detect_femm()
    if femm_installation is not None:
        logger.info(
            "Detected FEMM at %s (via %s).",
            femm_installation.install_root,
            femm_installation.route.value,
        )
    # FEMM absent is normal and is not logged -- see detect_femm()'s docstring.
    return aedt_installation, unsupported_aedt_installation


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

    # M10 Task 2: what this machine actually has, logged once through the
    # redacting logger above (never `print`, since an install root is an
    # absolute path -- exactly the text `RedactingFormatter` exists for).
    # Detection never imports PyAEDT or starts a desktop; see
    # `adapters/system/installations.py`'s module docstring for why.
    aedt_installation, unsupported_aedt_installation = log_detected_installations(logger)

    args = _parse_args(sys.argv[1:])
    if args.check_solver_imports:
        # Before the QGuiApplication: this is a console report about this
        # build, and it must work with no display at all.
        from inductor_designer.adapters.system.solver_imports import (
            check_solver_imports,
            format_solver_import_report,
        )

        report, ok = format_solver_import_report(check_solver_imports())
        print(report, file=sys.stderr, flush=True)
        return 0 if ok else 6
    _install_qml_logging()
    app = QGuiApplication(sys.argv)

    resources_refusal = _refuse_if_resources_are_missing(app, logger, args)
    if resources_refusal is not None:
        return resources_refusal

    preview_entries: list[PreviewEntry] | None = None
    simulation_summary: list[str] = []
    generation_controller: GenerationController | None = None
    recovery_controller: RecoveryController | None = None
    diagnostics_controller: DiagnosticsController | None = None
    project: InductorProject | None = None
    project_lock: ProjectLock | None = None
    from inductor_designer.ui.generation_lines import GenerationBackend

    # Checked on every launch, not just a launch with a document: a blank
    # project still needs the catalog for the core list and the matrix for the
    # backend gates. `_refuse_if_resources_are_missing` above covers the
    # shipped defaults; these two catch an explicit flag pointing nowhere.
    if not args.catalog.is_file():
        print("Catalog index not found; run: python -m tools.build_catalog", file=sys.stderr)
        return 2
    if not args.matrix.is_file():
        print(f"Compatibility matrix not found: {args.matrix}", file=sys.stderr)
        return 2
    backend_choices = [backend.value for backend in GenerationBackend]

    if args.project is not None:
        from inductor_designer.adapters.system.project_lock import (
            LockOutcome,
            ProjectLock,
        )
        from inductor_designer.application.services.geometry_model import GeometryModelError

        if not args.project.is_file():
            print(f"Project file not found: {args.project}", file=sys.stderr)
            return 4

        project_lock = ProjectLock(args.project)
        lock_outcome = project_lock.acquire()
        if lock_outcome is LockOutcome.HELD_BY_LIVE_PROCESS:
            holder = project_lock.holder
            assert holder is not None
            if holder.same_host:
                refusal = (
                    f"{args.project.name} is already open in another window "
                    f"(process {holder.pid}).\n\nClose it there first, then "
                    "start this one again."
                )
            else:
                refusal = (
                    f"{args.project.name} is already open on host "
                    f"{holder.host} (process {holder.pid}).\n\nWhether that "
                    "window is still running cannot be checked from here, so "
                    "close it on that machine, or delete the lock file beside "
                    "the project if that machine has crashed."
                )
            # Both channels: stderr for a terminal launch, the CLI and CI, and
            # a window for the shortcut launch that would otherwise show
            # nothing at all.
            print(refusal.replace("\n\n", " "), file=sys.stderr)
            logger.info("Launch refused: the project is already open elsewhere.")
            refusal_engine = show_launch_refusal(refusal)
            if refusal_engine.rootObjects():
                app.exec()
            return 5
        if lock_outcome is LockOutcome.TAKEN_FROM_STALE:
            # The ordinary aftermath of the crash this whole area exists to
            # survive: the previous owner's process is gone, so its lock is
            # taken rather than left to block this launch. See
            # `project_lock.py`'s module docstring for why a stale lock must
            # never refuse to start.
            logger.info(
                "Cleared a stale project lock for %s (previous owner is no "
                "longer running).",
                args.project,
            )

        try:
            project = _load_project(args.project)
            preview_entries = _load_preview_entries(project, args.catalog)
            simulation_summary = _load_simulation_summary(project)
        except GeometryModelError as error:
            for issue in error.issues:
                print(issue, file=sys.stderr)
            project_lock.release()
            return 3
        print(
            f"Loaded {args.project.name}: {len(preview_entries) - 1} winding(s); opening viewer.",
            file=sys.stderr,
            flush=True,
        )

    if project is None:
        # No `--project`: a blank unsaved project, not a dead shell. The
        # installer's shortcuts pass no arguments at all, and every screen
        # controller below is built from the session -- so without this the
        # core list, the windings, Preliminary, Simulation and Review are all
        # empty, and `File > Open`, gated on the session existing, cannot fix
        # it. `document_path` stays None until the first Save As, which is
        # also what keeps a run refused until the project is on disk.
        from inductor_designer.application.services.new_project import new_project

        project = new_project()

    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.materials import FileOverlayMaterialRepository
    from inductor_designer.adapters.persistence.project_repository import (
        ProjectRepository,
    )
    from inductor_designer.adapters.persistence.recovery_store import RecoveryStore
    from inductor_designer.adapters.persistence.schema_repository import (
        SchemaRepository,
    )
    from inductor_designer.adapters.system import resources
    from inductor_designer.adapters.system.environment import (
        catalog_overlay_directory,
        recovery_directory,
        seed_material_overlay,
        user_material_overlay_directory,
    )
    from inductor_designer.ui.diagnostics_controller import DiagnosticsController
    from inductor_designer.ui.material_studio_controller import MaterialStudioController
    from inductor_designer.ui.project_session import ProjectSession
    from inductor_designer.ui.recovery_controller import RecoveryController

    project_repository = ProjectRepository(SchemaRepository(resources.schemas_directory()))
    recovery_store = RecoveryStore(recovery_directory(), project_repository)

    def autosave_project(
        updated_project: InductorProject, document_path: Path | None
    ) -> None:
        recovery_store.write(updated_project, document_path)

    session = ProjectSession(
        project,
        args.project,
        open_callback=_load_project,
        autosave_callback=autosave_project,
        # The session tracks which slot its snapshot is in and passes it;
        # this used to be a variable here, and shipped two defects.
        recovery_cleanup=recovery_store.clear,
        lock=project_lock,
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
    # the project itself is unaffected. Safe for THIS document now that
    # the project lock above already refused a second window before
    # reaching this line -- no other process can be mid-run against
    # `args.project` when we get here. Residual, deliberately not closed
    # by this lock: `reconcile_unfinished_runs` scans the whole `runs/`
    # directory beside the document, and two different, unlocked
    # projects that happen to sit in the same folder still share that
    # one root -- a live run belonging to a NEIGHBOURING document could
    # still be reconciled away by this call. Closing that would mean
    # plumbing document identity into `run_recovery.py`, which this lock
    # does not touch.
    from inductor_designer.application.services.run_recovery import (
        reconcile_unfinished_runs,
    )

    # A project that has never been saved has no document, so there is no
    # `runs/` directory beside one to scan -- the blank project a launch with
    # no `--project` opens reaches here with `args.project` None.
    if args.project is not None:
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

    # The user's own materials live under the per-user data directory, not
    # inside the installed bundle: an upgrade rewrites the bundle, and until
    # 2026-09-04 that is where every imported material was written. The
    # shipped seed is copied across once, guarded on the destination not
    # existing, so a second launch can never overwrite a user's own material
    # with the seed.
    seed_material_overlay(resources.material_overlay_directory())
    material_repository = FileOverlayMaterialRepository(user_material_overlay_directory())
    material_studio_controller = MaterialStudioController(
        material_repository,
        pinned_revision=lambda: session.project.design.core_material,
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
    if generation_controller is not None:
        from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
        from inductor_designer.adapters.compatibility.matrix_repository import (
            MatrixCapabilityRepository,
        )
        from inductor_designer.ui.guided_studio_controller import GuidedStudioController

        # One catalog reader and one material overlay reader, shared by every
        # screen: a material imported in the Material Studio window (which
        # shares `material_repository` above) is visible to the Core &
        # Material selector without a process restart.
        # Shipped index plus the user's own imported cores, behind the one
        # catalog port every screen already reads. Cores the user imports are
        # therefore visible to Windings, Preliminary, Simulation and the
        # exporters without any of them knowing an overlay exists.
        catalog_repository = OverlayCatalogRepository(
            SqliteCatalogRepository(args.catalog), catalog_overlay_directory()
        )
        capabilities = MatrixCapabilityRepository(args.matrix).snapshot_for(
            SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION
        )
        guided_studio_controller = GuidedStudioController(session, catalog_repository)
        core_material_controller = CoreMaterialController(
            session, catalog_repository, material_repository
        )
        preliminary_controller = PreliminaryController(session, catalog_repository)
        simulation_controller = SimulationController(
            session,
            generation_controller,
            capabilities,
            aedt_installation,
            unsupported_aedt_installation,
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
        session.release_lock()
        return 1
    # Raise the window to the front so it is not lost behind the terminal.
    window = roots[0]
    if hasattr(window, "raise_"):
        window.raise_()
    if hasattr(window, "requestActivate"):
        window.requestActivate()
    # Release whichever document lock the session currently holds (Open can
    # have swapped it since launch) on every normal way the application
    # quits -- the Exit menu item and the window's close button both route
    # through `window.close()`, which ends the last window and triggers this
    # same signal. A lock left behind by a crash instead is handled by the
    # stale-lock path on the next launch, not by anything here.
    app.aboutToQuit.connect(session.release_lock)
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
