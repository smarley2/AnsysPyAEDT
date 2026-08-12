"""No QGuiApplication: the converter is testable without a running Qt app.

The PySide6 extra is still needed at import time -- the palette lives in
`ui.preview_geometry`, which is a Qt module -- so the import is guarded and
these tests skip rather than fail collection on an install without the extra.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

pytest.importorskip("PySide6")

from inductor_designer.application.services.geometry_model import (  # noqa: E402
    build_geometry_model,
)
from inductor_designer.domain.project import WindingOperatingPoint  # noqa: E402
from inductor_designer.domain.winding import CurrentDirection, WindingDirection  # noqa: E402
from inductor_designer.simulation.maxwell_plan import Polarity  # noqa: E402
from inductor_designer.simulation.plan_builder2d import build_maxwell2d_plan  # noqa: E402
from inductor_designer.simulation.run_contracts import effective_winding_inputs  # noqa: E402
from inductor_designer.ui.cut_plane_view import build_cut_plane_drawing  # noqa: E402
from inductor_designer.ui.preview_geometry import build_preview_entries  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_operating_point,
    make_project,
    make_winding,
)


def test_every_planar_conductor_becomes_one_circle_in_millimetres() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    planar_conductors = [
        conductor
        for winding in model.planar.windings
        for conductor in winding.conductors
    ]
    assert len(drawing.circles) == len(planar_conductors)
    assert drawing.r_inner_mm == model.planar.r_inner_m * 1000.0
    assert drawing.r_outer_mm == model.planar.r_outer_m * 1000.0
    assert drawing.depth_mm == model.planar.depth_m * 1000.0

    by_position = {
        (round(c.x_mm, 6), round(c.y_mm, 6)): c for c in drawing.circles
    }
    for conductor in planar_conductors:
        key = (round(conductor.x_m * 1000.0, 6), round(conductor.y_m * 1000.0, 6))
        assert key in by_position
        assert by_position[key].radius_mm == conductor.radius_m * 1000.0


def test_reversing_the_current_swaps_every_glyph() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)
    forward = build_cut_plane_drawing(model, project)

    reversed_points = tuple(
        replace(point, current_direction=CurrentDirection.REVERSE)
        for point in project.operating_point.windings
    )
    reversed_project = replace(
        project,
        operating_point=replace(project.operating_point, windings=reversed_points),
    )
    reversed_drawing = build_cut_plane_drawing(model, reversed_project)

    assert [c.into_plane for c in reversed_drawing.circles] == [
        not c.into_plane for c in forward.circles
    ]


def test_the_two_legs_of_a_turn_carry_opposite_glyphs() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    inner = [c for c in drawing.circles if math.hypot(c.x_mm, c.y_mm) < drawing.r_inner_mm]
    outer = [c for c in drawing.circles if math.hypot(c.x_mm, c.y_mm) > drawing.r_outer_mm]
    assert inner and outer
    assert len({c.into_plane for c in inner}) == 1
    assert len({c.into_plane for c in outer}) == 1
    assert inner[0].into_plane is not outer[0].into_plane


def test_winding_colour_matches_the_three_d_preview_order() -> None:
    """The 2D drawing and the 3D preview must colour each winding alike.

    `build_preview_entries` colours winding i by its index in
    `sorted(model.packings, key=winding_id)`; `build_cut_plane_drawing` must
    use that same order over `planar.windings`. A single-winding project
    can't tell the two orders apart -- index 0 either way -- so this builds
    two windings, "w2" declared before "w1", whose winding_id order is the
    reverse of their declaration order. That mismatch is what makes a
    missing (or divergent) sort observable.
    """
    project = make_project(
        design=replace(
            make_project().design,
            windings=(
                make_winding(winding_id="w2", start_angle_deg=0.0, sector_deg=150.0),
                make_winding(winding_id="w1", start_angle_deg=180.0, sector_deg=150.0),
            ),
        ),
        operating_point=make_operating_point(
            WindingOperatingPoint(
                winding_id="w2",
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=5.0,
                current_direction=CurrentDirection.FORWARD,
            ),
            WindingOperatingPoint(
                winding_id="w1",
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=5.0,
                current_direction=CurrentDirection.FORWARD,
            ),
        ),
    )
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)
    # entries[0] is the core; entries[1:] follow sorted(model.packings, key=winding_id).
    preview_entries = build_preview_entries(model)

    by_position = {(round(c.x_mm, 6), round(c.y_mm, 6)): c for c in drawing.circles}
    sorted_ids = sorted(w.winding_id for w in model.planar.windings)
    assert sorted_ids == ["w1", "w2"]  # declaration order was "w2", "w1"

    for index, winding_id in enumerate(sorted_ids):
        expected_color = preview_entries[1 + index].color
        planar_winding = next(w for w in model.planar.windings if w.winding_id == winding_id)
        assert planar_winding.conductors
        for conductor in planar_winding.conductors:
            key = (round(conductor.x_m * 1000.0, 6), round(conductor.y_m * 1000.0, 6))
            assert by_position[key].color == expected_color


def test_a_winding_wound_the_other_way_flips_its_own_glyphs() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)
    original = build_cut_plane_drawing(model, project)

    flipped_windings = tuple(
        replace(winding, winding_direction=WindingDirection.CLOCKWISE)
        if winding.winding_direction is WindingDirection.COUNTERCLOCKWISE
        else replace(winding, winding_direction=WindingDirection.COUNTERCLOCKWISE)
        for winding in project.design.windings
    )
    flipped = replace(
        project, design=replace(project.design, windings=flipped_windings)
    )

    flipped_drawing = build_cut_plane_drawing(model, flipped)

    assert [c.into_plane for c in flipped_drawing.circles] == [
        not c.into_plane for c in original.circles
    ]


def test_extent_covers_the_outermost_conductor_edge() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    furthest = max(
        math.hypot(c.x_mm, c.y_mm) + c.radius_mm for c in drawing.circles
    )
    assert drawing.extent_mm >= furthest
    assert drawing.extent_mm >= drawing.r_outer_mm


def test_a_design_without_conductors_still_draws_the_annulus() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)
    empty_model = replace(
        model, planar=replace(model.planar, windings=()), packings=()
    )

    drawing = build_cut_plane_drawing(empty_model, project)

    assert drawing.circles == ()
    assert drawing.r_outer_mm == model.planar.r_outer_m * 1000.0
    assert drawing.extent_mm == drawing.r_outer_mm
    assert "no conductors" in drawing.note


def test_the_drawing_and_the_two_d_export_describe_the_same_conductors() -> None:
    """The invariant the whole preview exists to protect.

    The drawing reads `operating_point.windings[].current_direction`; the
    export reads `EffectiveWindingInput.current_direction`. They agree only
    because `effective_winding_inputs` copies that field verbatim. Should it
    ever derive the value instead, the picture and the exported model would
    part ways in silence -- this is the test that would notice.
    """
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)
    plan = build_maxwell2d_plan(
        model.planar,
        project.design.windings,
        effective_winding_inputs(project.operating_point),
        model.bare_diameter_m,
        frequency_hz=project.operating_point.frequency_hz,
        recipe=project.simulation_recipe,
        material_record=make_material_record(),
        material_bh_series_id=None,
    )

    drawn = sorted(
        (circle.x_mm, circle.y_mm, circle.radius_mm, circle.into_plane)
        for circle in drawing.circles
    )
    exported = sorted(
        (
            conductor.x_m * 1000.0,
            conductor.y_m * 1000.0,
            conductor.radius_m * 1000.0,
            conductor.polarity is Polarity.NEGATIVE,
        )
        for group in plan.windings
        for conductor in group.conductors
    )
    assert drawn
    assert drawn == exported


def test_the_note_states_where_the_depth_comes_from() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    assert "half height" in drawing.note
    assert f"{drawing.depth_mm:.2f}" in drawing.note
