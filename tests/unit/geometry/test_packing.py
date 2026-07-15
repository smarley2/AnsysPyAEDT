from __future__ import annotations

import math

import pytest

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackingError, WindingSpec, pack_winding
from inductor_designer.geometry.turn_path import turn_loop_length_m

CORE = FinishedCore(r_inner_m=0.00973, r_outer_m=0.01683, half_height_m=0.005715,
                    corner_radius_m=0.0)
D = 0.001118


def spec(**overrides: object) -> WindingSpec:
    values: dict[str, object] = {
        "winding_id": "w1",
        "turns": 20,
        "insulated_diameter_m": D,
        "start_deg": 0.0,
        "sector_deg": 300.0,
        "min_spacing_m": 0.0001,
        "min_clearance_m": 0.001,
    }
    values.update(overrides)
    return WindingSpec(**values)  # type: ignore[arg-type]


def min_pitch_rad(layer: int) -> float:
    r_k = CORE.r_inner_m - (layer - 0.5) * D
    return 2 * math.asin((D + 0.0001) / (2 * r_k))


def test_single_layer_fit() -> None:
    packed = pack_winding(CORE, spec(turns=20))
    assert len(packed.layers) == 1
    layer = packed.layers[0]
    assert len(layer.station_deg) == 20
    assert layer.pitch_deg >= layer.min_pitch_deg
    margin = math.degrees(min_pitch_rad(1))
    for station in layer.station_deg:
        assert 0.0 + margin <= station <= 300.0 - margin


def test_overflow_opens_second_layer() -> None:
    usable = math.radians(300.0) - 2 * min_pitch_rad(1)
    capacity_1 = math.floor(usable / min_pitch_rad(1))
    packed = pack_winding(CORE, spec(turns=capacity_1 + 5))
    assert len(packed.layers) == 2
    assert len(packed.layers[0].station_deg) == capacity_1
    assert len(packed.layers[1].station_deg) == 5
    assert packed.layers[1].radial_build_m == pytest.approx(1.5 * D)


def test_infeasible_reports_max_turns() -> None:
    with pytest.raises(PackingError) as excinfo:
        pack_winding(CORE, spec(turns=100000))
    assert excinfo.value.winding_id == "w1"
    max_turns = excinfo.value.max_turns
    assert 0 < max_turns < 100000
    packed = pack_winding(CORE, spec(turns=max_turns))
    assert sum(len(layer.station_deg) for layer in packed.layers) == max_turns


def test_wire_length_analytic() -> None:
    # Each turn is one closed loop (reviewed decision); no connector wire.
    packed = pack_winding(CORE, spec(turns=10))
    loops = 10 * turn_loop_length_m(CORE, 1, D)
    leads = 2 * 3 * D
    assert packed.wire_length_m == pytest.approx(loops + leads, rel=1e-9)


def test_full_circle_sector_reserves_lead_gap() -> None:
    packed = pack_winding(CORE, spec(turns=5, sector_deg=360.0))
    margin = math.degrees(min_pitch_rad(1))
    for station in packed.layers[0].station_deg:
        assert margin <= station <= 360.0 - margin


def test_determinism() -> None:
    assert pack_winding(CORE, spec()) == pack_winding(CORE, spec())


def test_zero_capacity_sector() -> None:
    with pytest.raises(PackingError) as excinfo:
        pack_winding(CORE, spec(turns=1, sector_deg=10.0))
    assert excinfo.value.max_turns == 0
