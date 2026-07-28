from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    RunOutcome,
    generate_run,
    run_manifest_json,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.domain.project import InductorProject, MaterialRevisionSelection
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.run_contracts import (
    DimensionalRepresentation,
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project
from tests.unit.simulation.test_maxwell_plan import make_multi_bh_material_record

OUTPUT_DIRECTORY = Path("outputs/m6")
GOLDEN_DIRECTORY = Path(__file__).parents[2] / "golden"
GOLDEN_FILES = {
    RunBackend.MAXWELL_3D: "m6-maxwell3d-run-manifest.json",
    RunBackend.MAXWELL_2D: "m6-maxwell2d-run-manifest.json",
    RunBackend.FEMM: "m6-femm-run-manifest.json",
}
CAPABILITIES = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="Task 7 golden test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def project_for_runs() -> InductorProject:
    project = make_project()
    material = make_multi_bh_material_record()
    return replace(
        project,
        design=replace(
            project.design,
            core_material=MaterialRevisionSelection(
                ref=material.ref,
                revision_id=material.revision_id,
                snapshot=material,
                bh_series_id="bh-100c",
            ),
        ),
        operating_point=replace(
            project.operating_point,
            frequency_hz=125_000.0,
            winding_temperature_c=45.0,
            core_temperature_c=80.0,
            windings=(
                replace(
                    project.operating_point.windings[0],
                    ac_phase_deg=30.0,
                    dc_current_a=0.0,
                ),
            ),
        ),
    )


def generate_all_backends() -> dict[RunBackend, RunOutcome]:
    project = project_for_runs()
    maxwell3d = RecordingMaxwell3dExporter()
    maxwell2d = RecordingMaxwell2dExporter()
    femm = RecordingFemmSolver()
    outcomes: dict[RunBackend, RunOutcome] = {}
    for backend in RunBackend:
        outcomes[backend] = generate_run(
            project,
            RunRequest(backend, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            OUTPUT_DIRECTORY,
            maxwell3d_exporter=maxwell3d,
            maxwell2d_exporter=maxwell2d,
            femm_solver=femm,
            run_id=f"m6-{backend.value}",
            application_version="0.6.0-test",
        )
    assert len(maxwell3d.requests) == 1
    assert len(maxwell3d.geometry_only_requests) == 0
    assert len(maxwell2d.requests) == 1
    assert len(femm.requests) == 1
    assert str(maxwell3d.requests[0].release) == "2025.2"
    assert str(maxwell2d.requests[0].release) == "2025.2"
    assert femm.requests[0].analyze is False
    return outcomes


def test_generate_only_manifests_match_golden_and_share_physical_inputs() -> None:
    outcomes = generate_all_backends()
    manifests = [outcome.manifest for outcome in outcomes.values()]

    for manifest in manifests:
        assert manifest.project_id == "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c"
        assert manifest.frequency_hz == 125_000.0
        assert manifest.winding_temperature_c == 45.0
        assert manifest.core_temperature_c == 80.0
        assert len(manifest.windings) == 1
        winding = manifest.windings[0]
        assert winding.winding_id == "w1"
        assert winding.ac_rms_current_a == 2.0
        assert winding.ac_peak_current_a == pytest.approx(2.0 * math.sqrt(2.0))
        assert winding.phase_deg == 30.0
        assert winding.dc_current_a == 0.0
        assert manifest.material.revision_id == "0123456789ab"
        assert manifest.material.bh_series_id == "bh-100c"
        assert [output.value for output in manifest.requested_outputs] == [
            "resistance",
            "inductance",
        ]
        assert manifest.maximum_passes == 10
        assert manifest.percent_error == 1.0
        assert manifest.stages
        assert manifest.artifacts
        assert manifest.status is RunStatus.SUCCEEDED
        assert manifest.results is None

    assert outcomes[RunBackend.MAXWELL_3D].manifest.dimensional_representation is (
        DimensionalRepresentation.THREE_DIMENSIONAL
    )
    for backend in (RunBackend.MAXWELL_2D, RunBackend.FEMM):
        manifest = outcomes[backend].manifest
        assert manifest.dimensional_representation is (
            DimensionalRepresentation.EQUIVALENT_CROSS_SECTION
        )
        assert any("approximate" in warning for warning in manifest.warnings)

    for backend, outcome in outcomes.items():
        expected = (GOLDEN_DIRECTORY / GOLDEN_FILES[backend]).read_text(
            encoding="utf-8"
        )
        assert run_manifest_json(outcome.manifest) == expected


@pytest.mark.parametrize("backend", tuple(RunBackend))
def test_generate_and_solve_blocks_before_every_adapter_call(
    backend: RunBackend,
) -> None:
    maxwell3d = RecordingMaxwell3dExporter()
    maxwell2d = RecordingMaxwell2dExporter()
    femm = RecordingFemmSolver()

    with pytest.raises(
        MaxwellExportBlocked,
        match=(
            r"^Generate and Solve execution belongs to M8; "
            r"M6 only validates its Run Request\.$"
        ),
    ):
        generate_run(
            project_for_runs(),
            RunRequest(backend, RunMode.GENERATE_AND_SOLVE),
            CATALOG,
            CAPABILITIES,
            OUTPUT_DIRECTORY,
            maxwell3d_exporter=maxwell3d,
            maxwell2d_exporter=maxwell2d,
            femm_solver=femm,
            run_id="blocked",
            application_version="0.6.0-test",
        )

    assert maxwell3d.requests == []
    assert maxwell3d.geometry_only_requests == []
    assert maxwell2d.requests == []
    assert femm.requests == []


def test_confirmed_unresolved_run_uses_geometry_only_adapter_boundary() -> None:
    project = project_for_runs()
    project = replace(
        project,
        design=replace(project.design, core_material=None),
    )
    maxwell3d = RecordingMaxwell3dExporter()

    outcome = generate_run(
        project,
        RunRequest(
            RunBackend.MAXWELL_3D,
            RunMode.GENERATE_ONLY,
            confirm_geometry_only=True,
        ),
        CATALOG,
        CAPABILITIES,
        OUTPUT_DIRECTORY,
        maxwell3d_exporter=maxwell3d,
        maxwell2d_exporter=RecordingMaxwell2dExporter(),
        femm_solver=RecordingFemmSolver(),
        run_id="m6-geometry-only",
        application_version="0.6.0-test",
    )

    assert maxwell3d.requests == []
    assert len(maxwell3d.geometry_only_requests) == 1
    assert tuple(stage.name for stage in outcome.adapter_result.stages) == (
        "launch",
        "units",
        "core",
        "windings",
        "save",
    )
    assert outcome.manifest.geometry_only is True
    assert outcome.manifest.material.resolved is False
    assert outcome.manifest.results is None
