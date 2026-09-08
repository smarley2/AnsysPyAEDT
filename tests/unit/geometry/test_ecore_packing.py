"""Turns wound on an E core's centre leg, inside the winding window.

Design: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

The direct analogue of the toroid's angular packer: layers build outward from
the leg face, turns sit along the leg, and the refusal names the layer that
could not take the wire. Two windings share the window by taking different
spans, exactly as two windings share a toroid by taking different sectors.
"""

from __future__ import annotations

import pytest

from inductor_designer.geometry.ecore.body import FinishedECore
from inductor_designer.geometry.ecore.packing import (
    LegPackingError,
    LegWindingSpec,
    pack_leg_winding,
)

CORE = FinishedECore(
    centre_leg_width_m=0.0170,
    depth_m=0.0210,
    window_width_m=0.0092,
    window_height_m=0.0187,
    outer_leg_width_m=0.0085,
    yoke_thickness_m=0.0093,
)


def _spec(**overrides: object) -> LegWindingSpec:
    values: dict[str, object] = {
        "winding_id": "w1",
        "turns": 10,
        "insulated_diameter_m": 0.0011,
        "window_start_m": 0.0,
        "window_span_m": 0.0187,
        "min_spacing_m": 0.0002,
        "min_clearance_m": 0.001,
    }
    values.update(overrides)
    return LegWindingSpec(**values)  # type: ignore[arg-type]


def test_a_single_layer_holds_what_the_span_allows() -> None:
    """Turns per layer is the span divided by the wire pitch: 18.7 mm of
    window at a 1.3 mm pitch (1.1 mm wire plus 0.2 mm spacing) is 14 turns."""
    packed = pack_leg_winding(CORE, _spec(turns=14))
    assert len(packed.layers) == 1
    assert len(packed.layers[0].station_m) == 14
    # Stations are inside the span, in order, and pitched by the wire.
    stations = packed.layers[0].station_m
    assert stations == tuple(sorted(stations))
    assert stations[0] >= 0.0
    assert stations[-1] <= 0.0187
    assert packed.layers[0].pitch_m == pytest.approx(0.0013, rel=1e-9)


def test_turns_beyond_one_layer_start_a_second_one() -> None:
    """And the second layer sits one wire diameter further from the leg."""
    packed = pack_leg_winding(CORE, _spec(turns=20))
    assert len(packed.layers) == 2
    assert len(packed.layers[0].station_m) == 14
    assert len(packed.layers[1].station_m) == 6
    assert packed.layers[1].offset_m == pytest.approx(
        packed.layers[0].offset_m + 0.0011, rel=1e-9
    )


def test_a_winding_too_big_for_the_window_is_refused_by_layer() -> None:
    """The window is 9.2 mm wide less the 1 mm clearance, so at 1.1 mm per
    layer it takes 7 layers of 14 -- 98 turns fit and 200 do not. The refusal
    carries the number that did fit, like the toroid's does."""
    with pytest.raises(LegPackingError) as raised:
        pack_leg_winding(CORE, _spec(turns=200))
    assert raised.value.winding_id == "w1"
    assert raised.value.max_turns > 0
    assert "window" in str(raised.value)


def test_a_wire_thicker_than_the_window_cannot_even_start() -> None:
    with pytest.raises(LegPackingError, match="layer 1"):
        pack_leg_winding(CORE, _spec(insulated_diameter_m=0.020))


def test_a_span_too_short_for_one_turn_is_refused() -> None:
    with pytest.raises(LegPackingError, match="span"):
        pack_leg_winding(CORE, _spec(window_span_m=0.0005))


def test_two_windings_taking_different_spans_do_not_share_a_station() -> None:
    """The window analogue of two windings taking different sectors."""
    lower = pack_leg_winding(
        CORE, _spec(winding_id="w1", turns=6, window_start_m=0.0, window_span_m=0.009)
    )
    upper = pack_leg_winding(
        CORE, _spec(winding_id="w2", turns=6, window_start_m=0.010, window_span_m=0.0087)
    )
    assert max(lower.layers[0].station_m) < min(upper.layers[0].station_m)


def test_the_wire_length_counts_every_turn_around_the_leg() -> None:
    """One turn at the leg face is the rounded rectangle around it, so ten
    turns is ten of those -- the number a DC resistance depends on."""
    packed = pack_leg_winding(CORE, _spec(turns=10))
    perimeter = 2.0 * (0.0170 + 0.0210)
    assert packed.wire_length_m > 10 * perimeter
    # And not absurdly more: the corner arcs add a wire circumference or so
    # per turn, not a factor.
    assert packed.wire_length_m < 10 * (perimeter + 0.02)


def test_a_winding_running_past_the_leg_is_refused_by_the_model() -> None:
    """Found by review: `LegPlacement` and the schema bound the span below but
    not above, and nothing checked `start + span` against the leg, so turns
    were placed -- and drawn -- inside the yoke."""
    from dataclasses import replace

    from inductor_designer.application.services.geometry_model import (
        GeometryModelError,
        build_ecore_geometry_model,
    )
    from inductor_designer.domain.winding import LegPlacement, WindingLeg
    from tests.unit.application.test_geometry_model import CATALOG
    from tests.unit.application.test_geometry_model_ecore import _ecore_project

    project = _ecore_project()
    winding = replace(
        project.design.windings[0],
        placement=LegPlacement(
            # The leg is 2 * 18.7 = 37.4 mm; this runs to 48.7 mm.
            leg=WindingLeg.CENTRE,
            window_start_m=0.030,
            window_span_m=0.0187,
        ),
    )
    project = replace(project, design=replace(project.design, windings=(winding,)))

    with pytest.raises(GeometryModelError, match="centre leg"):
        build_ecore_geometry_model(project, CATALOG)


def test_two_windings_claiming_the_same_span_are_refused() -> None:
    """The window analogue of the toroid's sector-overlap rule, which
    `domain/validation._sectors_overlap` cannot express for a leg. Without it
    both windings packed to identical stations and occupied the same copper."""
    from dataclasses import replace

    from inductor_designer.application.services.geometry_model import (
        GeometryModelError,
        build_ecore_geometry_model,
    )
    from inductor_designer.domain.project import WindingOperatingPoint
    from inductor_designer.domain.winding import CurrentDirection
    from tests.unit.application.test_geometry_model import CATALOG
    from tests.unit.application.test_geometry_model_ecore import _ecore_project

    project = _ecore_project(turns=6)
    first = project.design.windings[0]
    second = replace(first, winding_id="w2", turns=6)
    project = replace(
        project,
        design=replace(project.design, windings=(first, second)),
        operating_point=replace(
            project.operating_point,
            windings=(
                project.operating_point.windings[0],
                WindingOperatingPoint("w2", 0.0, 0.0, 0.0, CurrentDirection.FORWARD),
            ),
        ),
    )

    with pytest.raises(GeometryModelError, match="same span"):
        build_ecore_geometry_model(project, CATALOG)


def test_the_clearance_is_taken_out_of_the_usable_window() -> None:
    """Found by review: setting `usable = window_width_m` (ignoring the
    clearance entirely) passed every test in this file. The clearance is the
    gap the wire must keep from the outer leg it faces, so it costs layers."""
    # 9.2 mm of window less 1 mm of clearance leaves 8.2 mm: 7 layers of
    # 1.1 mm wire, 14 turns each, 98 in all. Less 6 mm of clearance leaves
    # 3.2 mm: 2 layers, so 28.
    assert len(pack_leg_winding(CORE, _spec(turns=28, min_clearance_m=0.006)).layers) == 2
    with pytest.raises(LegPackingError, match="window"):
        pack_leg_winding(CORE, _spec(turns=29, min_clearance_m=0.006))

    # The same 29 turns fit when the clearance is small, so the refusal above
    # is the clearance doing its job and not the window width alone -- which
    # is the mutation (`usable = window_width_m`) this test exists to catch.
    assert pack_leg_winding(CORE, _spec(turns=29, min_clearance_m=0.001)) is not None
