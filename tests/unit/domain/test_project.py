from __future__ import annotations

import pytest

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from tests.unit.domain.test_catalog_records import make_core


def make_winding(**overrides: object) -> WindingDefinition:
    values: dict[str, object] = {
        "winding_id": "w1",
        "label": "Primary",
        "turns": 20,
        "conductor_name": "AWG 18",
        "mode": ConductorMode.SOLID,
        "start_angle_deg": 0.0,
        "sector_deg": 150.0,
        "min_spacing_m": 0.0002,
        "min_clearance_m": 0.001,
        "winding_direction": WindingDirection.CLOCKWISE,
        "current_direction": CurrentDirection.FORWARD,
        "terminal_intent": "",
        "ac_magnitude_a": 2.0,
        "ac_phase_deg": 0.0,
        "frequency_hz": 100_000.0,
        "dc_current_a": 5.0,
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def make_project(**overrides: object) -> InductorProject:
    values: dict[str, object] = {
        "project_id": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "name": "Boost inductor",
        "description": "",
        "target_release": AedtRelease(2025, 2),
        "target_edition": AedtEdition.COMMERCIAL,
        "dimension_mode": ModelDimension.THREE_D,
        "core": CatalogCoreSelection("0077071A7", make_core(), ()),
        "windings": (make_winding(),),
    }
    values.update(overrides)
    return InductorProject(**values)  # type: ignore[arg-type]


def test_project_aggregate_holds_selection_and_windings() -> None:
    project = make_project()
    assert isinstance(project.core, CatalogCoreSelection)
    assert project.windings[0].turns == 20


def test_catalog_selection_rejects_part_number_mismatch() -> None:
    with pytest.raises(ValueError, match="part_number"):
        CatalogCoreSelection("9999", make_core(), ())


def test_manual_selection_and_empty_core_allowed() -> None:
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0)
    assert make_project(core=manual).core is manual
    assert make_project(core=None).core is None


def test_winding_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="winding_id"):
        make_winding(winding_id="  ")


def test_project_rejects_blank_name() -> None:
    with pytest.raises(ValueError, match="name"):
        make_project(name=" ")


def test_override_carries_reason() -> None:
    override = CoreOverride(field="outer_diameter_m", value=0.027, reason="measured sample")
    assert override.reason == "measured sample"
