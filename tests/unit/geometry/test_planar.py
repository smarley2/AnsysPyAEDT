from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import WindingSpec, pack_winding
from inductor_designer.geometry.planar import build_planar_model

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118
BARE_R = 0.00102362 / 2


def test_planar_model_projects_stations() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 6, D, 0.0, 180.0, 0.0001, 0.001))
    model = build_planar_model(CORE, [packing], {"w1": BARE_R})
    assert model.r_inner_m == CORE.r_inner_m
    assert model.r_outer_m == CORE.r_outer_m
    assert model.depth_m == pytest.approx(2 * CORE.half_height_m)
    winding = model.windings[0]
    assert len(winding.conductors) == 12  # 6 turns x (inner + outer)
    inner = [c for c in winding.conductors if c.polarity == 1]
    outer = [c for c in winding.conductors if c.polarity == -1]
    assert len(inner) == len(outer) == 6
    for conductor in inner:
        r = math.hypot(conductor.x_m, conductor.y_m)
        assert r == pytest.approx(CORE.r_inner_m - D / 2, rel=1e-6)
        assert conductor.radius_m == BARE_R
    for conductor in outer:
        r = math.hypot(conductor.x_m, conductor.y_m)
        assert r == pytest.approx(CORE.r_outer_m + D / 2, rel=1e-6)


def test_second_layer_projects_deeper() -> None:
    packing = pack_winding(CORE, WindingSpec("w1", 40, D, 0.0, 300.0, 0.0001, 0.001))
    assert len(packing.layers) >= 2
    model = build_planar_model(CORE, [packing], {"w1": BARE_R})
    radii = sorted(
        round(math.hypot(c.x_m, c.y_m), 6)
        for c in model.windings[0].conductors
        if c.polarity == 1
    )
    assert radii[0] < radii[-1]  # layer-2 inner conductors sit deeper in the window
