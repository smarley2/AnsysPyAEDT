from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
)
from inductor_designer.application.ports.maxwell2d_exporter import (
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    Maxwell3dGeometryOnlyRequest,
    MaxwellExportResult,
)
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    RunGenerationFailed,
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
    ManifestStage,
    RunBackend,
    RunMode,
    RunRequest,
    RunStatus,
    StageStatus,
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


def test_femm_generate_only_ignores_mismatched_aedt_capability_snapshot() -> None:
    maxwell3d = RecordingMaxwell3dExporter()
    maxwell2d = RecordingMaxwell2dExporter()
    femm = RecordingFemmSolver()
    mismatched = replace(CAPABILITIES, release=AedtRelease(2026, 1))

    outcome = generate_run(
        project_for_runs(),
        RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
        CATALOG,
        mismatched,
        OUTPUT_DIRECTORY,
        maxwell3d_exporter=maxwell3d,
        maxwell2d_exporter=maxwell2d,
        femm_solver=femm,
        run_id="m6-femm-independent",
        application_version="0.6.0-test",
    )

    assert outcome.manifest.status is RunStatus.SUCCEEDED
    assert maxwell3d.requests == []
    assert maxwell3d.geometry_only_requests == []
    assert maxwell2d.requests == []
    assert len(femm.requests) == 1


class RaisingMaxwell3dExporter(RecordingMaxwell3dExporter):
    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        raise RuntimeError("maxwell-3d adapter boom")

    def export_geometry_only(
        self, request: Maxwell3dGeometryOnlyRequest
    ) -> Maxwell3dExportResult:
        raise RuntimeError("maxwell-3d geometry-only adapter boom")


class RaisingMaxwell2dExporter(RecordingMaxwell2dExporter):
    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult:
        raise RuntimeError("maxwell-2d adapter boom")


class RaisingFemmSolver(RecordingFemmSolver):
    def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
        raise RuntimeError("femm adapter boom")


@pytest.mark.parametrize(
    ("backend", "geometry_only", "diagnostic"),
    [
        (RunBackend.MAXWELL_3D, False, "RuntimeError: maxwell-3d adapter boom"),
        (
            RunBackend.MAXWELL_3D,
            True,
            "RuntimeError: maxwell-3d geometry-only adapter boom",
        ),
        (RunBackend.MAXWELL_2D, False, "RuntimeError: maxwell-2d adapter boom"),
        (RunBackend.FEMM, False, "RuntimeError: femm adapter boom"),
    ],
)
def test_adapter_exception_carries_failed_manifest_evidence(
    backend: RunBackend,
    geometry_only: bool,
    diagnostic: str,
) -> None:
    project = project_for_runs()
    if geometry_only:
        project = replace(
            project,
            design=replace(project.design, core_material=None),
        )
    request = RunRequest(
        backend,
        RunMode.GENERATE_ONLY,
        confirm_geometry_only=geometry_only,
    )

    with pytest.raises(RunGenerationFailed) as raised:
        generate_run(
            project,
            request,
            CATALOG,
            CAPABILITIES,
            OUTPUT_DIRECTORY,
            maxwell3d_exporter=RaisingMaxwell3dExporter(),
            maxwell2d_exporter=RaisingMaxwell2dExporter(),
            femm_solver=RaisingFemmSolver(),
            run_id=f"failed-{backend.value}",
            application_version="0.6.0-test",
        )

    failure = raised.value
    manifest = failure.manifest
    assert failure.planned_run.request is request
    assert manifest.status is RunStatus.FAILED
    assert manifest.geometry_only is geometry_only
    assert manifest.stages == (
        ManifestStage(
            name="generate",
            status=StageStatus.FAILED,
            diagnostic=diagnostic,
        ),
    )
    assert manifest.diagnostics == (diagnostic,)
    assert manifest.artifacts == ()
    assert manifest.results is None
    assert manifest.windings[0].ac_rms_current_a == 2.0
    assert manifest.windings[0].ac_peak_current_a == pytest.approx(
        2.0 * math.sqrt(2.0)
    )
    assert manifest.adapter_version is None
    assert manifest.solver_version is None


def _wrong_femm_result() -> FemmSolveResult:
    return FemmSolveResult(
        fem_path=Path("outputs/wrong.fem"),
        analyzed=True,
        results={},
        messages=("wrong-result",),
        adapter_version="wrong-femm-adapter",
        solver_version="wrong-femm-solver",
    )


class WrongResultMaxwell3dExporter(RecordingMaxwell3dExporter):
    def export(self, request: Maxwell3dExportRequest) -> FemmSolveResult:
        return _wrong_femm_result()


class WrongResultMaxwell2dExporter(RecordingMaxwell2dExporter):
    def export(self, request: Maxwell2dExportRequest) -> FemmSolveResult:
        return _wrong_femm_result()


class WrongResultFemmSolver(RecordingFemmSolver):
    def solve(self, request: FemmSolveRequest) -> MaxwellExportResult:
        return MaxwellExportResult(
            project_path=Path("outputs/wrong.aedt"),
            design_name="WrongResult",
            pyaedt_version="wrong-maxwell-adapter",
            stages=(),
        )


@pytest.mark.parametrize(
    ("backend", "diagnostic"),
    [
        (
            RunBackend.MAXWELL_3D,
            "TypeError: Maxwell run returned a non-Maxwell adapter result.",
        ),
        (
            RunBackend.MAXWELL_2D,
            "TypeError: Maxwell run returned a non-Maxwell adapter result.",
        ),
        (
            RunBackend.FEMM,
            "TypeError: FEMM run returned a non-FEMM adapter result.",
        ),
    ],
)
def test_wrong_adapter_result_carries_failed_manifest_evidence(
    backend: RunBackend,
    diagnostic: str,
) -> None:
    with pytest.raises(RunGenerationFailed) as raised:
        generate_run(
            project_for_runs(),
            RunRequest(backend, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            OUTPUT_DIRECTORY,
            maxwell3d_exporter=WrongResultMaxwell3dExporter(),
            maxwell2d_exporter=WrongResultMaxwell2dExporter(),
            femm_solver=WrongResultFemmSolver(),
            run_id=f"wrong-result-{backend.value}",
            application_version="0.6.0-test",
        )

    failure = raised.value
    manifest = failure.manifest
    assert isinstance(failure.__cause__, TypeError)
    assert manifest.status is RunStatus.FAILED
    assert manifest.stages == (
        ManifestStage(
            name="generate",
            status=StageStatus.FAILED,
            diagnostic=diagnostic,
        ),
    )
    assert manifest.diagnostics == (diagnostic,)
    assert manifest.artifacts == ()
    assert manifest.results is None
    assert manifest.windings[0].ac_rms_current_a == 2.0
    assert manifest.adapter_version is None
    assert manifest.solver_version is None


class NonconformingFemmSolver(RecordingFemmSolver):
    def __init__(
        self,
        *,
        analyzed: bool,
        results_present: bool,
    ) -> None:
        super().__init__()
        self._analyzed = analyzed
        self._results_present = results_present

    def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
        result = super().solve(request)
        return replace(
            result,
            analyzed=self._analyzed,
            results={} if self._results_present else None,
        )


@pytest.mark.parametrize(
    ("analyzed", "results_present"),
    [(True, False), (False, True), (True, True)],
)
def test_nonconforming_femm_generate_only_result_is_failed_evidence(
    analyzed: bool,
    results_present: bool,
) -> None:
    solver = NonconformingFemmSolver(
        analyzed=analyzed,
        results_present=results_present,
    )

    with pytest.raises(RunGenerationFailed) as raised:
        generate_run(
            project_for_runs(),
            RunRequest(RunBackend.FEMM, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            OUTPUT_DIRECTORY,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=solver,
            run_id="failed-femm-contract",
            application_version="0.6.0-test",
        )

    failure = raised.value
    diagnostic = (
        "FEMM Generate Only adapter returned nonconforming evidence: "
        f"analyzed={analyzed}, results_present={results_present}."
    )
    manifest = failure.manifest
    assert manifest.status is RunStatus.FAILED
    assert manifest.stages[0].name == "generate"
    assert manifest.stages[0].status is StageStatus.FAILED
    assert manifest.stages[0].diagnostic == diagnostic
    assert manifest.diagnostics == (diagnostic,)
    assert manifest.artifacts == ()
    assert manifest.results is None
    assert manifest.adapter_version == "recording-fake"
    assert manifest.solver_version is None
    assert len(solver.requests) == 1
