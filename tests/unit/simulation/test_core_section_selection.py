from __future__ import annotations

from dataclasses import replace

from inductor_designer.domain.winding import ToroidPlacement, WindingDefinition
from inductor_designer.simulation.section_selection import select_core_sections
from tests.unit.domain.test_project import make_project


def windings(*spans: tuple[float, float]) -> tuple[WindingDefinition, ...]:
    base = make_project().design.windings[0]
    return tuple(
        replace(base, winding_id=f"w{index}", placement=ToroidPlacement(
            start_angle_deg=start,
            sector_deg=sector,
        ))
        for index, (start, sector) in enumerate(spans, start=1)
    )


def azimuths(sections: object) -> list[float]:
    return [section.azimuth_deg for section in sections]  # type: ignore[attr-defined]


def features(sections: object) -> list[str]:
    return [section.feature for section in sections]  # type: ignore[attr-defined]


def test_one_full_cover_winding_yields_start_and_midpoint_only() -> None:
    sections = select_core_sections(windings((0.0, 360.0)))

    assert azimuths(sections) == [0.0, 180.0]
    assert features(sections) == ["span-start", "span-mid"]


def test_a_partial_winding_adds_the_uncovered_gap_midpoint() -> None:
    sections = select_core_sections(windings((0.0, 180.0)))

    assert azimuths(sections) == [0.0, 90.0, 180.0, 270.0]
    assert features(sections)[-1] == "gap-mid"


def test_two_disjoint_sectors_produce_two_gap_midpoints() -> None:
    sections = select_core_sections(windings((0.0, 90.0), (180.0, 90.0)))

    gaps = [
        section.azimuth_deg  # type: ignore[attr-defined]
        for section in sections
        if section.feature == "gap-mid"  # type: ignore[attr-defined]
    ]
    assert gaps == [135.0, 315.0]


def test_a_wrapping_sector_is_handled_as_one_span() -> None:
    sections = select_core_sections(windings((350.0, 40.0)))

    assert 350.0 in azimuths(sections)
    assert 30.0 in azimuths(sections)


def test_planes_closer_than_the_tolerance_collapse_to_one() -> None:
    sections = select_core_sections(windings((0.0, 180.0), (180.3, 179.7)))

    values = azimuths(sections)
    assert len(values) == len(set(values))
    assert all(
        later - earlier >= 0.5 for earlier, later in zip(values, values[1:], strict=False)
    )


def test_a_span_start_wins_over_a_colliding_span_end() -> None:
    sections = select_core_sections(windings((0.0, 180.0), (180.0, 180.0)))

    at_180 = [
        section
        for section in sections
        if section.azimuth_deg == 180.0  # type: ignore[attr-defined]
    ]
    assert len(at_180) == 1
    assert at_180[0].feature in {"span-start", "span-end"}  # type: ignore[attr-defined]


def test_identifiers_are_stable_and_ordered() -> None:
    first = select_core_sections(windings((0.0, 120.0)))
    second = select_core_sections(windings((0.0, 120.0)))

    ids = [section.section_id for section in first]  # type: ignore[attr-defined]
    assert ids == [section.section_id for section in second]  # type: ignore[attr-defined]
    assert ids[0].startswith("core.00.")
    assert ids[1].startswith("core.01.")


def test_no_winding_produces_no_section() -> None:
    assert select_core_sections(()) == ()
