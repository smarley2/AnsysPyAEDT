"""The cut plane, drawn from an outline rather than a pair of radii.

Design: `docs/superpowers/specs/2026-09-04-m11a-gapped-e-core-design.md`.

One renderer, both families. Keeping `r_inner_mm`/`r_outer_mm` and adding
rectangles beside them would leave every drawing half-populated, which is the
monolith this milestone exists to avoid -- so the core becomes a list of
shapes, painted in order, and the toroid emits exactly the two circles it
always drew.
"""

from __future__ import annotations

import pytest

from inductor_designer.application.services.geometry_model import (
    build_ecore_geometry_model,
    build_geometry_model,
)
from inductor_designer.ui.cut_plane_view import (
    CutPlaneCircleOutline,
    CutPlaneRect,
    build_cut_plane_drawing,
    build_ecore_cut_plane_drawing,
)
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_geometry_model_ecore import _ecore_project
from tests.unit.domain.test_project import make_project


def test_a_toroid_still_draws_its_annulus_as_two_circles() -> None:
    """The outline is a generalisation, not a change: same two shapes, same
    radii, painted in the same order -- outer disc, then the bore cut back
    out."""
    project = make_project()
    drawing = build_cut_plane_drawing(build_geometry_model(project, CATALOG), project)

    outer, bore = drawing.outline
    assert isinstance(outer, CutPlaneCircleOutline)
    assert isinstance(bore, CutPlaneCircleOutline)
    assert outer.cutout is False
    assert bore.cutout is True
    assert outer.radius_mm > bore.radius_mm > 0.0


def test_an_e_core_draws_its_legs_and_yokes_as_rectangles() -> None:
    project = _ecore_project()
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )

    solids = [
        shape
        for shape in drawing.outline
        if isinstance(shape, CutPlaneRect) and not shape.cutout
    ]
    # Centre leg, two yokes, two outer legs.
    assert len(solids) == 5
    # The centre leg is the tallest shape on the axis: it spans both halves'
    # windows (2D = 37.4 mm), where a yoke is only its own thickness.
    centre = max(
        (shape for shape in solids if shape.x_mm == 0.0),
        key=lambda shape: shape.height_mm,
    )
    assert centre.width_mm == pytest.approx(17.0)
    assert centre.height_mm == pytest.approx(37.4)
    # The yokes span the whole outline width: A = F + 2E + 2G = 52.4 mm.
    yokes = [shape for shape in solids if shape.width_mm == pytest.approx(52.4)]
    assert len(yokes) == 2
    assert sorted(round(shape.y_mm, 6) for shape in yokes) == [-23.35, 23.35]


def test_each_gap_is_a_break_in_the_centre_leg() -> None:
    """Drawn, not implied: the gap is the whole point of the design, and a
    reader has to see where the iron stops."""
    project = _ecore_project(gaps_m=(0.0005, 0.0005), gap_spacings_m=(0.004,))
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )

    breaks = [
        shape
        for shape in drawing.outline
        if isinstance(shape, CutPlaneRect) and shape.cutout
    ]
    assert len(breaks) == 2
    assert all(shape.height_mm == pytest.approx(0.5) for shape in breaks)
    # Separated by the 4 mm segment of core the user asked for.
    lower, upper = sorted(breaks, key=lambda shape: shape.y_mm)
    assert upper.y_mm - lower.y_mm == pytest.approx(4.5)


def test_the_turns_appear_on_both_sides_of_the_leg() -> None:
    """A turn wraps the leg, so a section through it cuts the wire twice --
    once each side, with opposite polarity, exactly as a toroid's turn is cut
    at its bore and its outside."""
    project = _ecore_project(turns=6)
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )

    assert len(drawing.circles) == 12
    left = [circle for circle in drawing.circles if circle.x_mm < 0.0]
    right = [circle for circle in drawing.circles if circle.x_mm > 0.0]
    assert len(left) == len(right) == 6
    assert {circle.into_plane for circle in left} != {
        circle.into_plane for circle in right
    }


def test_an_ungapped_pair_has_no_breaks_and_says_so() -> None:
    project = _ecore_project(gaps_m=())
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )
    assert not [
        shape
        for shape in drawing.outline
        if isinstance(shape, CutPlaneRect) and shape.cutout
    ]
    assert "ungapped" in drawing.note.lower()


def test_a_gapped_pair_states_the_total_gap_on_the_drawing() -> None:
    """The number a reader would otherwise have to add up from the fields."""
    project = _ecore_project(gaps_m=(0.0005, 0.0005), gap_spacings_m=(0.004,))
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )
    assert "1.00 mm" in drawing.note


def test_the_gap_stack_is_centred_on_the_joint_between_the_halves() -> None:
    """Found by review: moving the stack's origin to zero (drawing every gap
    from the leg's centre outward instead of centring the stack on the joint)
    passed every test here -- the separation was checked, the position was
    not. The joint is where the halves meet, so that is where a ground gap
    physically is."""
    project = _ecore_project(gaps_m=(0.001,))
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )
    (break_,) = [shape for shape in drawing.outline if shape.cutout]
    # One gap, so it straddles the joint: centred on y = 0.
    assert break_.y_mm == pytest.approx(0.0, abs=1e-9)

    two = _ecore_project(gaps_m=(0.001, 0.001), gap_spacings_m=(0.004,))
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(two, CATALOG), two
    )
    breaks = sorted(
        (shape for shape in drawing.outline if shape.cutout),
        key=lambda shape: shape.y_mm,
    )
    # Two gaps and the segment between them, symmetric about the joint.
    assert breaks[0].y_mm == pytest.approx(-breaks[1].y_mm, rel=1e-9)


def test_the_turns_sit_outside_the_iron_not_inside_it() -> None:
    """Found by review: drawing the conductors at `leg_half - offset - r`
    (inside the centre leg) passed every test here. Copper inside the iron is
    not a drawing anyone can check a design against."""
    project = _ecore_project(turns=6)
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )
    leg_half_mm = 17.0 / 2.0
    for circle in drawing.circles:
        assert abs(circle.x_mm) - circle.radius_mm >= leg_half_mm - 1e-9, circle


def test_the_shim_build_draws_breaks_in_the_outer_legs_too() -> None:
    """Suspected by review, confirmed: `outer_legs_gapped` puts gaps in the
    network's outer-leg branch, and the drawing showed those legs continuous
    -- a picture disagreeing with the numbers printed beside it."""
    project = _ecore_project(gaps_m=(0.001,), outer_legs_gapped=True)
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )
    breaks = [shape for shape in drawing.outline if shape.cutout]
    # One in the centre leg, one in each outer leg.
    assert len(breaks) == 3
    assert sorted(round(shape.x_mm, 6) for shape in breaks)[1] == 0.0
    assert all(shape.height_mm == pytest.approx(1.0) for shape in breaks)


def test_the_ground_centre_leg_build_leaves_the_outer_legs_whole() -> None:
    project = _ecore_project(gaps_m=(0.001,), outer_legs_gapped=False)
    drawing = build_ecore_cut_plane_drawing(
        build_ecore_geometry_model(project, CATALOG), project
    )
    breaks = [shape for shape in drawing.outline if shape.cutout]
    assert len(breaks) == 1
    assert breaks[0].x_mm == 0.0
