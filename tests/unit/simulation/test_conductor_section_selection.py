from __future__ import annotations

import math

from inductor_designer.simulation.section_selection import (
    select_conductor_sections,
    skin_depth_m,
)
from inductor_designer.simulation.sections import CONDUCTOR_STATIONS
from tests.unit.simulation.test_plan_builder import CORE


def select(**overrides: object) -> tuple[object, ...]:
    base: dict[str, object] = {
        "core": CORE,
        "winding_id": "w1",
        "turn_count": 9,
        "wire_radius_m": 1e-3,
        "insulated_diameter_m": 2.2e-3,
        "layer": 1,
        "station_deg": 10.0,
        "frequency_hz": 0.0,
        "winding_temperature_c": 25.0,
    }
    base.update(overrides)
    return select_conductor_sections(**base)  # type: ignore[arg-type]


def test_skin_depth_falls_with_frequency() -> None:
    low = skin_depth_m(1_000.0, 25.0)
    high = skin_depth_m(1_000_000.0, 25.0)

    assert low is not None and high is not None
    assert low > high


def test_skin_depth_is_infinite_at_dc() -> None:
    assert skin_depth_m(0.0, 25.0) == math.inf


def test_skin_depth_is_none_outside_the_validated_copper_range() -> None:
    assert skin_depth_m(100_000.0, 200.0) is None


def test_dc_uses_one_disc_on_the_middle_turn() -> None:
    sections = select(frequency_hz=0.0)

    assert len(sections) == 1
    assert sections[0].station == "inner-bore"  # type: ignore[attr-defined]
    assert sections[0].turn_index == 4  # type: ignore[attr-defined]


def test_a_thick_skin_depth_still_uses_one_disc() -> None:
    # 1 kHz in copper is about 2 mm of skin depth, wider than a 0.5 mm wire.
    sections = select(frequency_hz=1_000.0, wire_radius_m=5e-4)

    assert len(sections) == 1


def test_a_thin_skin_depth_escalates_to_four_stations() -> None:
    sections = select(frequency_hz=1_000_000.0, wire_radius_m=2e-3)

    assert tuple(section.station for section in sections) == CONDUCTOR_STATIONS  # type: ignore[attr-defined]


def test_an_unevaluable_gate_escalates_conservatively() -> None:
    sections = select(frequency_hz=100_000.0, winding_temperature_c=200.0)

    assert len(sections) == 4


def test_the_middle_turn_is_deterministic_for_both_parities() -> None:
    assert select(turn_count=8)[0].turn_index == 3  # type: ignore[attr-defined]
    assert select(turn_count=9)[0].turn_index == 4  # type: ignore[attr-defined]


def test_every_disc_is_perpendicular_to_the_wire() -> None:
    for section in select(frequency_hz=1_000_000.0, wire_radius_m=2e-3):
        length = math.sqrt(sum(component**2 for component in section.normal))  # type: ignore[attr-defined]
        assert math.isclose(length, 1.0, rel_tol=1e-9)


def test_stations_sit_at_distinct_points_on_the_turn() -> None:
    centers = {
        section.center_m  # type: ignore[attr-defined]
        for section in select(frequency_hz=1_000_000.0, wire_radius_m=2e-3)
    }

    assert len(centers) == 4


def test_identifiers_name_the_winding_turn_and_station() -> None:
    assert select()[0].section_id == "winding.w1.turn04.inner-bore"  # type: ignore[attr-defined]


def test_a_winding_with_no_turns_produces_no_section() -> None:
    assert select(turn_count=0) == ()
