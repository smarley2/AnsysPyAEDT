"""An E-core project, through geometry and into the estimate.

Design: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

Two families, two models: the toroid builder keeps its exact type and refuses
an E-core project by name rather than growing a second shape. That refusal is
what keeps `geometry/toroid/` from learning what a leg is -- the milestone's
own rule -- and it is asserted here, not assumed.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.geometry_model import (
    GeometryModelError,
    build_ecore_geometry_model,
    build_geometry_model,
)
from inductor_designer.application.services.preliminary_inputs import (
    core_magnetic_properties,
)
from inductor_designer.domain.project import InductorProject, ManualECoreSelection
from inductor_designer.domain.winding import LegPlacement, WindingLeg
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project, make_winding

E_CORE = ManualECoreSelection(
    centre_leg_width_m=0.0170,
    depth_m=0.0210,
    window_width_m=0.0092,
    window_height_m=0.0187,
    outer_leg_width_m=0.0085,
    yoke_thickness_m=0.0093,
    gaps_m=(0.001,),
)


def _ecore_project(turns: int = 20, **core_overrides: object) -> InductorProject:
    project = make_project()
    winding = make_winding(
        turns=turns,
        placement=LegPlacement(
            leg=WindingLeg.CENTRE, window_start_m=0.0, window_span_m=0.0187
        ),
    )
    return replace(
        project,
        design=replace(
            project.design,
            core=replace(E_CORE, **core_overrides) if core_overrides else E_CORE,
            windings=(winding,),
            core_material=None,
        ),
    )


def test_the_toroid_builder_refuses_an_e_core_project_by_name() -> None:
    """Not a crash and not a silent empty model: the message says which
    builder to use, because both are legitimate and the project decides."""
    with pytest.raises(GeometryModelError) as raised:
        build_geometry_model(_ecore_project(), CATALOG)
    assert any("E core" in issue for issue in raised.value.issues)


def test_an_e_core_project_builds_its_own_model() -> None:
    model = build_ecore_geometry_model(_ecore_project(), CATALOG)
    assert model.body.total_gap_m == pytest.approx(0.001)
    (packed,) = model.packings
    assert sum(len(layer.station_m) for layer in packed.layers) == 20


def test_a_winding_that_does_not_fit_the_window_refuses_with_its_reason() -> None:
    with pytest.raises(GeometryModelError) as raised:
        build_ecore_geometry_model(_ecore_project(turns=5000), CATALOG)
    assert any("window" in issue for issue in raised.value.issues)


def test_the_estimate_reads_the_network_and_reports_no_inductance_factor() -> None:
    """A manual core has no published A_L, exactly as a manual toroid has
    none, so the cross-check reports itself unavailable instead of comparing
    against a number nobody published."""
    properties = core_magnetic_properties(E_CORE)
    assert properties is not None
    assert properties.al_value_nh is None
    assert properties.gap_length_m == pytest.approx(0.001)
    # Iron path, referred to the centre-leg area (hand-computed in
    # tests/unit/geometry/test_ecore_reluctance.py).
    assert properties.path_length_m == pytest.approx(0.154047311827957, rel=1e-9)
    assert properties.effective_area_m2 == pytest.approx(0.000357, rel=1e-9)
    assert any("gap" in note.lower() for note in properties.notes)


def test_an_ungapped_pair_reports_no_gap_at_all() -> None:
    """So the estimate takes its ungapped path, unchanged."""
    properties = core_magnetic_properties(replace(E_CORE, gaps_m=()))
    assert properties is not None
    assert properties.gap_length_m == 0.0
