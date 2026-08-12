"""No Qt import: the converter is testable without a QGuiApplication."""

from __future__ import annotations

import math
from dataclasses import replace

from inductor_designer.application.services.geometry_model import build_geometry_model
from inductor_designer.domain.winding import CurrentDirection, WindingDirection
from inductor_designer.ui.cut_plane_view import build_cut_plane_drawing
from inductor_designer.ui.preview_geometry import PALETTE
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project


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
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    first_id = sorted(w.winding_id for w in model.planar.windings)[0]
    first_circles = [
        c
        for c in drawing.circles
        if c.color == PALETTE[0]
    ]
    assert first_circles
    expected = len(
        next(w for w in model.planar.windings if w.winding_id == first_id).conductors
    )
    assert len(first_circles) == expected


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


def test_the_note_states_where_the_depth_comes_from() -> None:
    project = make_project()
    model = build_geometry_model(project, CATALOG)

    drawing = build_cut_plane_drawing(model, project)

    assert "half height" in drawing.note
    assert f"{drawing.depth_mm:.2f}" in drawing.note
