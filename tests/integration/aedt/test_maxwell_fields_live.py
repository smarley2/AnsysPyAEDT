"""M8c live evidence: B and J come off the representative cross sections.

    set INDUCTOR_AEDT_RELEASE=2025.2
    set INDUCTOR_AEDT_EDITION=commercial
    .venv/Scripts/python.exe -m pytest -m aedt -q

This is where `Mag_B`, `Mag_J`, `"Integrate"` and `"Maximum"` are proven. A
name AEDT does not recognize shows up as a per-section diagnostic and an
unavailable quantity, so read results.json before concluding anything about
the physics.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.catalog.sqlite_repository import SqliteCatalogRepository
from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.adapters.pyaedt.maxwell3d import PyaedtMaxwell3dExporter
from inductor_designer.application.services.aedt_support import (
    SUPPORTED_AEDT_EDITION,
    SUPPORTED_AEDT_RELEASE,
)
from inductor_designer.application.services.project_run import start_project_run
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.result_vocabulary import (
    FIELD_QUANTITIES,
    SCALAR_QUANTITIES,
)
from inductor_designer.simulation.run_contracts import (
    ResultAvailability,
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_maxwell_export import project_for_runs
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.aedt


@pytest.mark.parametrize("backend", (RunBackend.MAXWELL_3D, RunBackend.MAXWELL_2D))
def test_a_solved_run_reports_field_sections_and_aggregates(
    tmp_path: Path, backend: RunBackend
) -> None:
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    edition = os.environ.get("INDUCTOR_AEDT_EDITION")
    if not release or not edition:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION to run AEDT tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    project = project_for_runs()
    project = replace(
        project,
        simulation_recipe=replace(
            project.simulation_recipe,
            requested_outputs=SCALAR_QUANTITIES + FIELD_QUANTITIES,
        ),
    )
    document_path = tmp_path / "fields.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    result = start_project_run(
        project,
        document_path,
        RunRequest(backend, RunMode.GENERATE_AND_SOLVE),
        catalog,
        capabilities,
        maxwell3d_exporter=(
            PyaedtMaxwell3dExporter()
            if backend is RunBackend.MAXWELL_3D
            else RecordingMaxwell3dExporter()
        ),
        maxwell2d_exporter=(
            PyaedtMaxwell2dExporter()
            if backend is RunBackend.MAXWELL_2D
            else RecordingMaxwell2dExporter()
        ),
        femm_solver=RecordingFemmSolver(),
        application_version="live-test",
    )

    manifest = result.outcome.manifest
    assert manifest.status is RunStatus.SUCCEEDED
    assert manifest.results is not None

    field_entries = [
        entry
        for entry in manifest.results.quantities
        if entry.quantity in FIELD_QUANTITIES
    ]
    assert field_entries, "a solved run reports the field quantities it was asked for"

    for entry in field_entries:
        if entry.availability is ResultAvailability.AVAILABLE:
            assert entry.unit and entry.provenance and entry.reason is None
        else:
            assert entry.value is None
            assert entry.reason is not None
            assert entry.reason.startswith(f"{entry.quantity.value}.")

    for scope_suffix in (
        "worst-section-mean",
        "area-weighted-average",
        "maximum",
    ):
        assert any(
            entry.scope.endswith(scope_suffix)
            and entry.quantity is RequestedOutput.FLUX_DENSITY
            for entry in field_entries
        ), f"the {scope_suffix} aggregate is always reported"

    exported = json.loads(
        (result.location.results_directory / "results.json").read_text(
            encoding="utf-8"
        )
    )
    assert exported["quantities"]


def test_the_extraction_saw_exactly_the_sections_selection_chose(
    tmp_path: Path,
) -> None:
    """Selection and extraction must not disagree about what was evaluated."""
    release = os.environ.get("INDUCTOR_AEDT_RELEASE")
    if not release:
        pytest.skip("Set INDUCTOR_AEDT_RELEASE and INDUCTOR_AEDT_EDITION to run AEDT tests")

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    project = project_for_runs()
    project = replace(
        project,
        simulation_recipe=replace(
            project.simulation_recipe,
            requested_outputs=(RequestedOutput.FLUX_DENSITY,),
        ),
    )
    document_path = tmp_path / "sections.inductor.json"
    document_path.write_text("{}", encoding="utf-8")
    capabilities = MatrixCapabilityRepository(
        ROOT / "compatibility" / "aedt-matrix.yml"
    ).snapshot_for(SUPPORTED_AEDT_RELEASE, SUPPORTED_AEDT_EDITION)

    result = start_project_run(
        project,
        document_path,
        RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_AND_SOLVE),
        catalog,
        capabilities,
        maxwell3d_exporter=PyaedtMaxwell3dExporter(),
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        application_version="live-test",
    )

    plan = result.outcome.planned_run.solver_plan
    manifest = result.outcome.manifest
    assert manifest.results is not None
    reported = {
        entry.scope
        for entry in manifest.results.quantities
        if ".section." in entry.scope
        and entry.quantity is RequestedOutput.FLUX_DENSITY
    }
    assert len(reported) == len(plan.core_sections)  # type: ignore[union-attr]
