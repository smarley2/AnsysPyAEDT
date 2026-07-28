from __future__ import annotations

import math

import pytest

from inductor_designer.domain.project import MeshIntent, RequestedOutput
from inductor_designer.simulation.run_contracts import (
    CurrentConvention,
    DimensionalRepresentation,
    ManifestArtifact,
    ManifestMaterialState,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
    ResultQuantity,
    RunBackend,
    RunManifest,
    RunMode,
    RunRequest,
    RunStatus,
    effective_winding_inputs,
)
from tests.unit.domain.test_project import make_project


def make_manifest(**overrides: object) -> RunManifest:
    project = make_project()
    values: dict[str, object] = {
        "run_id": "run-1",
        "project_id": project.project_id,
        "project_schema_version": 5,
        "backend": RunBackend.MAXWELL_3D,
        "mode": RunMode.GENERATE_ONLY,
        "dimensional_representation": DimensionalRepresentation.THREE_DIMENSIONAL,
        "frequency_hz": project.operating_point.frequency_hz,
        "winding_temperature_c": project.operating_point.winding_temperature_c,
        "core_temperature_c": project.operating_point.core_temperature_c,
        "windings": effective_winding_inputs(project.operating_point),
        "material": ManifestMaterialState(
            resolved=True,
            ref=None,
            revision_id=None,
            bh_series_id=None,
            manual_compatibility_acknowledged=False,
        ),
        "mesh_intent": MeshIntent.STANDARD,
        "maximum_passes": 10,
        "percent_error": 1.0,
        "requested_outputs": (RequestedOutput.RESISTANCE,),
        "geometry_only": False,
        "application_version": "0.1.0",
        "solver_version": "2025 R2",
        "adapter_version": "0.1.0",
        "warnings": (),
        "stages": (),
        "status": RunStatus.PLANNED,
        "diagnostics": (),
        "artifacts": (),
        "results": None,
    }
    values.update(overrides)
    return RunManifest(**values)  # type: ignore[arg-type]


def test_run_contract_enum_values_are_stable() -> None:
    assert RunBackend.MAXWELL_3D.value == "maxwell-3d"
    assert RunBackend.MAXWELL_2D.value == "maxwell-2d"
    assert RunBackend.FEMM.value == "femm"
    assert RunMode.GENERATE_ONLY.value == "generate-only"
    assert RunMode.GENERATE_AND_SOLVE.value == "generate-and-solve"
    assert DimensionalRepresentation.EQUIVALENT_CROSS_SECTION.value == "equivalent-cross-section"
    assert ResultAvailability.AVAILABLE.value == "available"
    assert CurrentConvention.AC_RMS.value == "ac-rms"
    assert ResultQuantity is RequestedOutput


def test_run_request_defaults_to_unconfirmed_geometry_only() -> None:
    request = RunRequest(RunBackend.MAXWELL_3D, RunMode.GENERATE_ONLY)

    assert request.confirm_geometry_only is False


def test_effective_input_records_rms_and_peak() -> None:
    item = effective_winding_inputs(make_project().operating_point)[0]

    assert item.ac_rms_current_a == 2.0
    assert item.ac_peak_current_a == pytest.approx(2.0 * math.sqrt(2.0))


def test_available_result_requires_value_unit_and_provenance() -> None:
    with pytest.raises(ValueError, match="available result"):
        NormalizedQuantity(
            quantity=ResultQuantity.RESISTANCE,
            scope="w1",
            availability=ResultAvailability.AVAILABLE,
            value=None,
            unit="ohm",
            current_convention=CurrentConvention.AC_RMS,
            approximation=None,
            reason=None,
            provenance="",
        )


def test_unavailable_result_requires_reason_without_value() -> None:
    with pytest.raises(ValueError, match="unavailable result"):
        NormalizedQuantity(
            quantity=ResultQuantity.INDUCTANCE,
            scope="w1",
            availability=ResultAvailability.UNAVAILABLE,
            value=1.0,
            unit="H",
            current_convention=CurrentConvention.NOT_APPLICABLE,
            approximation=None,
            reason="",
            provenance=None,
        )


def test_geometry_only_manifest_requires_unresolved_maxwell_3d_generate_only() -> None:
    with pytest.raises(ValueError, match="Geometry-Only manifest"):
        make_manifest(geometry_only=True)


def test_succeeded_manifest_requires_artifact() -> None:
    with pytest.raises(ValueError, match="succeeded manifest"):
        make_manifest(status=RunStatus.SUCCEEDED)


def test_manifest_result_backend_matches_manifest_backend() -> None:
    results = NormalizedResultSet("run-1", RunBackend.FEMM, ())

    with pytest.raises(ValueError, match="result backend"):
        make_manifest(results=results)


def test_manifest_carries_successful_result_evidence() -> None:
    quantity = NormalizedQuantity(
        quantity=ResultQuantity.RESISTANCE,
        scope="w1",
        availability=ResultAvailability.AVAILABLE,
        value=0.25,
        unit="ohm",
        current_convention=CurrentConvention.AC_RMS,
        approximation=None,
        reason=None,
        provenance="Maxwell winding resistance",
    )
    results = NormalizedResultSet("run-1", RunBackend.MAXWELL_3D, (quantity,))

    manifest = make_manifest(
        status=RunStatus.SUCCEEDED,
        artifacts=(ManifestArtifact("aedt-project", "outputs/run-1.aedt"),),
        results=results,
    )

    assert manifest.results is results
