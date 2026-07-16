from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell3d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import ModelDimension
from inductor_designer.domain.project import ManualCoreSelection
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project, make_winding


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
    outcome = export_maxwell3d(three_d_project(), CATALOG, exporter, tmp_path)  # type: ignore[arg-type]
    assert outcome.result.succeeded()
    request = exporter.requests[0]
    assert request.project_name == "Boost_inductor"
    assert [g.name for g in request.plan.windings] == ["w1", "w2"]
    assert request.non_graphical is True


def test_two_d_project_is_blocked(tmp_path: Path) -> None:
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    with pytest.raises(MaxwellExportBlocked, match="3d"):
        export_maxwell3d(project, CATALOG, RecordingMaxwell3dExporter(), tmp_path)  # type: ignore[arg-type]


def test_manual_core_is_blocked(tmp_path: Path) -> None:
    project = replace(
        three_d_project(),  # type: ignore[type-var]
        core=ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
    )
    with pytest.raises(MaxwellExportBlocked, match="catalog cores"):
        export_maxwell3d(project, CATALOG, RecordingMaxwell3dExporter(), tmp_path)  # type: ignore[arg-type]


def test_manifest_is_deterministic_and_carries_stages(tmp_path: Path) -> None:
    exporter = RecordingMaxwell3dExporter()
    outcome = export_maxwell3d(three_d_project(), CATALOG, exporter, tmp_path)  # type: ignore[arg-type]
    manifest = generation_manifest_json(outcome)
    assert manifest == generation_manifest_json(outcome)
    payload = json.loads(manifest)
    assert payload["schemaVersion"] == 1
    assert payload["succeeded"] is True
    assert [stage["name"] for stage in payload["stages"]][0] == "launch"
    assert payload["windings"][0]["turnCount"] == 10
    assert any("Milestone 4" in note for note in payload["notes"])
