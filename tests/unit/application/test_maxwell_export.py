from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_femm2d,
    export_maxwell2d,
    export_maxwell3d,
    femm_manifest_json,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import ManualCoreSelection
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project, make_winding

SNAPSHOT = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=None,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)

NATIVE_SNAPSHOT = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def three_d_project() -> object:
    return replace(
        make_project(
            windings=(
                make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0, turns=10),
                make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0, turns=10),
            )
        ),
        dimension_mode=ModelDimension.THREE_D,
    )


def test_export_builds_plan_and_calls_exporter(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    outcome = export_maxwell3d(
        three_d_project(), CATALOG, exporter, tmp_path, capabilities=SNAPSHOT  # type: ignore[arg-type]
    )
    assert outcome.result.succeeded()
    request = exporter.requests[0]
    assert request.project_name == "Boost_inductor"
    assert [g.name for g in request.plan.windings] == ["w1", "w2"]
    assert request.non_graphical is True


def test_two_d_project_is_blocked(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    with pytest.raises(MaxwellExportBlocked, match="3d"):
        export_maxwell3d(
            project, CATALOG, RecordingMaxwell3dExporter(), tmp_path, capabilities=SNAPSHOT  # type: ignore[arg-type]
        )


def test_manual_core_is_blocked(tmp_path: Path) -> None:
    project = replace(
        three_d_project(),  # type: ignore[type-var]
        core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
    )
    with pytest.raises(MaxwellExportBlocked, match="catalog cores"):
        export_maxwell3d(
            project, CATALOG, RecordingMaxwell3dExporter(), tmp_path, capabilities=SNAPSHOT  # type: ignore[arg-type]
        )


def test_manifest_is_deterministic_and_carries_stages(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    outcome = export_maxwell3d(
        three_d_project(), CATALOG, exporter, tmp_path, capabilities=SNAPSHOT  # type: ignore[arg-type]
    )
    manifest = generation_manifest_json(outcome)
    assert manifest == generation_manifest_json(outcome)
    payload = json.loads(manifest)
    assert payload["schemaVersion"] == 2
    assert payload["succeeded"] is True
    assert [stage["name"] for stage in payload["stages"]][0] == "launch"
    assert payload["windings"][0]["turnCount"] == 10
    assert any(
        "The 3D Include DC Fields capability has not been reviewed for this environment."
        in note
        for note in payload["notes"]
    )
    assert payload["backend"] == "aedt"


def test_3d_manifest_v2_identifies_blocked_dc(tmp_path: Path) -> None:
    outcome = export_maxwell3d(
        three_d_project(), CATALOG, RecordingMaxwell3dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=SNAPSHOT,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["schemaVersion"] == 2
    assert payload["dimension"] == "3d"
    assert payload["dcBias"]["strategy"] == "blocked"
    assert payload["dcBias"]["appliedCurrentsA"] is None
    assert payload["capabilities"]["includeDcFields3d"] is None
    assert payload["capabilities"]["reviewStatus"] == "reviewed"


def test_3d_native_dc_applied_currents_in_manifest(tmp_path: Path) -> None:
    outcome = export_maxwell3d(
        three_d_project(), CATALOG, RecordingMaxwell3dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=NATIVE_SNAPSHOT,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["dcBias"]["strategy"] == "native-include-dc-fields"
    assert payload["dcBias"]["appliedCurrentsA"] == {"w1": 5.0, "w2": 5.0}
    assert outcome.plan.dc_bias is outcome.decision


def test_2d_export_blocked_dc_and_conductor_count(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    outcome = export_maxwell2d(
        project, CATALOG, RecordingMaxwell2dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=NATIVE_SNAPSHOT,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["dimension"] == "2d"
    assert payload["dcBias"]["strategy"] == "blocked"
    assert "Maxwell 2D" in payload["dcBias"]["reason"]
    assert payload["windings"][0]["conductorCount"] == 20
    assert any("approximate" in note for note in payload["notes"])


def test_2d_refuses_3d_project(tmp_path: Path) -> None:
    with pytest.raises(MaxwellExportBlocked, match="2d"):
        export_maxwell2d(
            three_d_project(), CATALOG, RecordingMaxwell2dExporter(), tmp_path,  # type: ignore[arg-type]
            capabilities=SNAPSHOT,
        )


def test_femm_export_happy_path(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    solver = RecordingFemmSolver()
    outcome = export_femm2d(
        project, CATALOG, solver, tmp_path, capabilities=SNAPSHOT  # type: ignore[arg-type]
    )
    assert outcome.result.analyzed is True
    request = solver.requests[0]
    assert request.project_name == "Boost_inductor_2d"

    manifest = femm_manifest_json(outcome)
    assert manifest == femm_manifest_json(outcome)
    payload = json.loads(manifest)
    assert payload["schemaVersion"] == 2
    assert payload["backend"] == "femm"
    assert payload["dimension"] == "2d"
    assert payload["designName"] == outcome.plan.design_name
    assert payload["femPath"] == str(outcome.result.fem_path)
    assert payload["analyzed"] is True
    assert payload["dcBias"]["strategy"] == "blocked"
    assert set(payload["femmResults"]) == {"w1", "w2"}
    assert payload["femmResults"]["w1"]["resistanceOhm"] == 0.1
    assert payload["windings"][0]["conductorCount"] == 20


def test_femm_export_not_analyzed_has_no_results(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    solver = RecordingFemmSolver()
    outcome = export_femm2d(
        project, CATALOG, solver, tmp_path,  # type: ignore[arg-type]
        capabilities=SNAPSHOT, analyze=False,
    )
    payload = json.loads(femm_manifest_json(outcome))
    assert payload["analyzed"] is False
    assert payload["femmResults"] is None
