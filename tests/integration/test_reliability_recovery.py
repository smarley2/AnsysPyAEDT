"""Task 9: forced-failure robustness, against the real catalog, the real
material overlay, and the recording exporter fakes in `tests/fakes/`.

Each test forces one of the four M9 recovery mechanisms to fail and proves the
roadmap 9 exit criterion directly: the last valid Project document survives,
and the evidence produced is sufficient for diagnosis and safe to share. No
AEDT, no FEMM -- every solver boundary here is a recording fake.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.catalog.sqlite_repository import (  # noqa: E402
    SqliteCatalogRepository,
)
from inductor_designer.adapters.materials.overlay_repository import (  # noqa: E402
    FileOverlayMaterialRepository,
)
from inductor_designer.adapters.persistence.project_repository import (  # noqa: E402
    ProjectRepository,
)
from inductor_designer.adapters.persistence.recovery_store import RecoveryStore  # noqa: E402
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository  # noqa: E402
from inductor_designer.adapters.system.diagnostic_archive import (  # noqa: E402
    collect_bundle_sources,
)
from inductor_designer.application.services.diagnostic_bundle import (  # noqa: E402
    build_bundle_entries,
)
from inductor_designer.application.services.project_run import (  # noqa: E402
    ProjectRunFailed,
    start_project_run,
)
from inductor_designer.application.services.redaction import RedactionContext  # noqa: E402
from inductor_designer.application.services.run_recovery import (  # noqa: E402
    INTERRUPTED_DIAGNOSTIC,
    UNSOLVED_ARTIFACT_DIAGNOSTIC,
    reconcile_unfinished_runs,
)
from inductor_designer.domain.project import InductorProject  # noqa: E402
from inductor_designer.materials.identity import MaterialRef  # noqa: E402
from inductor_designer.materials.records import MaterialRecord, SeriesKind  # noqa: E402
from inductor_designer.simulation.run_contracts import (  # noqa: E402
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from inductor_designer.ui.core_material_controller import CoreMaterialController  # noqa: E402
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.guided_studio_controller import GuidedStudioController  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.simulation_controller import SimulationController  # noqa: E402
from tests.fakes.femm_solver import RecordingFemmSolver  # noqa: E402
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter  # noqa: E402
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter  # noqa: E402
from tests.unit.application.test_maxwell_export import CAPABILITIES  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402
from tools.build_catalog import build  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]
REF = MaterialRef("Magnetics", "High Flux", "60")


def _application() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


def _real_catalog(tmp_path: Path) -> SqliteCatalogRepository:
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    return SqliteCatalogRepository(index)


def _bh_series_id(record: MaterialRecord) -> str:
    """Read the shipped series id; never predict one (it depends on the import)."""
    return next(
        series.series_id
        for series in record.series
        if series.kind is SeriesKind.BH_CURVE
    )


def _project_pinned_to_the_real_catalog_and_overlay(
    catalog: SqliteCatalogRepository,
) -> InductorProject:
    """A generate-ready project: a real catalog core and a real overlay revision."""
    materials = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = materials.list_revisions(REF)[0]
    series_id = _bh_series_id(materials.get(REF, revision_id))
    session = ProjectSession(make_project())
    core_material = CoreMaterialController(session, catalog, materials)
    assert core_material.selectMaterial(
        REF.manufacturer, REF.name, REF.grade, revision_id, series_id
    )
    compatible = [row["partNumber"] for row in core_material.coreOptions]
    assert compatible, "the shipped catalog has no core for the shipped material"
    assert core_material.selectCatalogCore(str(compatible[0]))
    return session.project


def test_a_save_that_fails_preserves_the_last_valid_project(tmp_path: Path) -> None:
    _application()
    document_path = tmp_path / "boost.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    store = RecoveryStore(
        tmp_path / "recovery", ProjectRepository(SchemaRepository(Path("schemas")))
    )

    def failing_save(project: InductorProject) -> None:
        raise OSError("simulated: disk full")

    session = ProjectSession(
        make_project(),
        document_path,
        failing_save,
        autosave_callback=lambda project, doc: store.write(project, doc),
    )
    edited = replace(session.project, description="edited while the disk is full")
    session.apply(edited)

    assert session.saveProject() is False
    assert session.project == edited
    assert session.dirty is True
    assert "disk full" in session.statusMessage
    assert document_path.read_text(encoding="utf-8") == "{}"

    session.flushAutosave()
    snapshot = store.read()
    assert snapshot is not None
    assert store.load_project(snapshot) == edited


def test_a_killed_solve_is_reconciled_and_never_re_solved(tmp_path: Path) -> None:
    document_path = tmp_path / "boost.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    run_directory = tmp_path / "runs" / "20260821-090000-maxwell-3d"
    run_directory.mkdir(parents=True)
    (run_directory / "run-manifest.json").write_text(
        json.dumps(
            {
                "runId": "20260821-090000",
                "backend": "maxwell-3d",
                "mode": "generate-and-solve",
                "status": "running",
                "startedUtc": "2026-08-21T09:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    saved_artifact = run_directory / "Inductor3D.aedt"
    saved_artifact.write_text("saved before the process was killed", encoding="utf-8")
    exporter = RecordingMaxwell3dExporter()

    reconciled = reconcile_unfinished_runs(document_path)

    assert len(reconciled) == 1
    document = json.loads((run_directory / "run-manifest.json").read_text(encoding="utf-8"))
    assert document["status"] == RunStatus.INTERRUPTED.value
    assert document["results"] is None
    diagnostics_text = " ".join(document["diagnostics"])
    assert INTERRUPTED_DIAGNOSTIC in diagnostics_text
    assert UNSOLVED_ARTIFACT_DIAGNOSTIC in diagnostics_text
    assert saved_artifact.is_file()
    assert (
        saved_artifact.read_text(encoding="utf-8")
        == "saved before the process was killed"
    )
    # Recovery reached no adapter: reconciliation reads and rewrites a manifest
    # file, and never calls the exporter that would re-solve the run. `exporter`
    # is never passed to `reconcile_unfinished_runs`, so these two lines cannot
    # fail by themselves; the artifact-content assertion above is the real
    # check that reconciliation never touched the solver's output.
    assert exporter.requests == []
    assert exporter.geometry_only_requests == []


def test_a_licence_failure_produces_actionable_redactable_evidence(
    tmp_path: Path,
) -> None:
    catalog = _real_catalog(tmp_path)
    project = _project_pinned_to_the_real_catalog_and_overlay(catalog)
    document_path = tmp_path / "boost.inductor.json"
    document_path.write_text("{}", encoding="utf-8")

    exporter = RecordingMaxwell3dExporter()

    def _fail_launch() -> None:
        raise RuntimeError("License checkout failed on 1055@LICSRV01")

    exporter.on_stage["launch"] = _fail_launch

    with pytest.raises(ProjectRunFailed) as failure:
        start_project_run(
            project,
            document_path,
            RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY),
            catalog,
            CAPABILITIES,
            maxwell3d_exporter=exporter,
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            application_version="0.9.0-test",
        )

    error = failure.value
    assert error.manifest.status is RunStatus.FAILED
    diagnostics_text = " ".join(error.manifest.diagnostics)
    assert "License checkout failed on 1055@LICSRV01" in diagnostics_text
    assert "license.unavailable:" in diagnostics_text

    # The run manifest alone never carries an absolute path (artifact paths are
    # written relative to the project directory), so a source that actually
    # contains one is added here: an application log line of the kind
    # `app_logging.py` writes, naming the failing document by its absolute
    # path. Without this, the "no absolute path in the bundle" half of the
    # exit criterion is unexercised by this test.
    log_path = tmp_path / "app.log"
    log_path.write_text(
        f"AEDT [launch]: failed while staging {document_path}\n",
        encoding="utf-8",
    )

    entries = build_bundle_entries(
        collect_bundle_sources(document_path, log_path),
        RedactionContext(),
        application_version="0.9.0-test",
        created_utc="2026-08-21T09:05:00+00:00",
    )
    bundle_text = "\n".join(entry.text for entry in entries)
    assert "license.unavailable" in bundle_text
    assert "1055@LICSRV01" not in bundle_text
    assert str(tmp_path) not in bundle_text


def test_undo_restores_the_last_valid_project_after_a_rejected_edit(
    tmp_path: Path,
) -> None:
    _application()
    catalog = _real_catalog(tmp_path)
    document_path = tmp_path / "boost.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    baseline = make_project()
    session = ProjectSession(baseline, document_path, lambda project: None)
    windings = GuidedStudioController(session, catalog)
    generation = GenerationController(lambda request: ("done",))
    simulation = SimulationController(session, generation, CAPABILITIES)

    assert simulation.canGenerate

    assert windings.addWinding()
    valid_project = session.project
    assert session.dirty
    assert not simulation.canGenerate

    added_winding_id = valid_project.design.windings[-1].winding_id
    assert not windings.setWindingField(added_winding_id, "startAngleDeg", "0")

    assert session.project == valid_project
    assert not simulation.canGenerate

    assert session.undo() is True
    assert session.project == baseline
    assert not session.dirty
    assert simulation.canGenerate
