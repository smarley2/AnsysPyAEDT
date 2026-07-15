from __future__ import annotations

import math

from hypothesis import given, settings
from hypothesis import strategies as st

from inductor_designer.geometry.core_solid import FinishedCore
from inductor_designer.geometry.packing import PackingError, WindingSpec, pack_winding
from inductor_designer.geometry.turn_path import turn_loop_length_m

cores = st.builds(
    FinishedCore,
    r_inner_m=st.floats(min_value=0.004, max_value=0.03),
    r_outer_m=st.floats(min_value=0.032, max_value=0.06),
    half_height_m=st.floats(min_value=0.002, max_value=0.02),
    corner_radius_m=st.just(0.0),
)

specs = st.builds(
    WindingSpec,
    winding_id=st.just("w"),
    turns=st.integers(min_value=1, max_value=300),
    insulated_diameter_m=st.floats(min_value=0.0002, max_value=0.003),
    start_deg=st.floats(min_value=0.0, max_value=359.0),
    sector_deg=st.floats(min_value=15.0, max_value=360.0),
    min_spacing_m=st.floats(min_value=0.0, max_value=0.0005),
    min_clearance_m=st.just(0.001),
)


@settings(max_examples=200, deadline=None)
@given(core=cores, spec=specs)
def test_packing_invariants(core: FinishedCore, spec: WindingSpec) -> None:
    try:
        packed = pack_winding(core, spec)
    except PackingError as error:
        assert 0 <= error.max_turns < spec.turns
        if error.max_turns > 0:
            refit = pack_winding(core, WindingSpec(
                spec.winding_id, error.max_turns, spec.insulated_diameter_m,
                spec.start_deg, spec.sector_deg, spec.min_spacing_m, spec.min_clearance_m,
            ))
            total = sum(len(layer.station_deg) for layer in refit.layers)
            assert total == error.max_turns
        return

    total = sum(len(layer.station_deg) for layer in packed.layers)
    assert total == spec.turns

    for layer in packed.layers:
        # stations inside the declared sector
        for station in layer.station_deg:
            assert spec.start_deg <= station <= spec.start_deg + spec.sector_deg
        # pitch respects the chord constraint
        assert layer.pitch_deg >= layer.min_pitch_deg - 1e-9
        # layer stays inside the bore
        r_k = core.r_inner_m - layer.radial_build_m
        assert r_k - spec.insulated_diameter_m / 2.0 > 0.0
        # stations strictly increasing
        assert all(
            b > a for a, b in zip(layer.station_deg, layer.station_deg[1:], strict=False)
        )
        # adjacent wire surfaces truly separated (chord distance at the bore circle)
        if len(layer.station_deg) >= 2:
            gap_rad = math.radians(layer.pitch_deg)
            chord = 2.0 * r_k * math.sin(gap_rad / 2.0)
            assert chord >= spec.insulated_diameter_m + spec.min_spacing_m - 1e-9

    # wire length lower bound: turns * single loop at layer 1
    floor_length = spec.turns * turn_loop_length_m(core, 1, spec.insulated_diameter_m)
    assert packed.wire_length_m >= floor_length - 1e-9


@settings(max_examples=100, deadline=None)
@given(core=cores, spec=specs)
def test_packing_is_deterministic(core: FinishedCore, spec: WindingSpec) -> None:
    try:
        first = pack_winding(core, spec)
    except PackingError:
        return
    assert first == pack_winding(core, spec)
