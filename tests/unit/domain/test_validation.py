from __future__ import annotations

from inductor_designer.domain.project import CatalogCoreSelection, CoreOverride, ManualCoreSelection
from inductor_designer.domain.validation import ValidationCategory, validate_project
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_project, make_winding


def codes(project: object, **kwargs: object) -> set[str]:
    return {issue.code for issue in validate_project(project, **kwargs)}  # type: ignore[arg-type]


def test_valid_project_has_no_errors() -> None:
    project = make_project(
        windings=(
            make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0),
            make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0),
        )
    )
    issues = validate_project(project, known_conductors={"AWG 18"})
    assert not [i for i in issues if i.category is ValidationCategory.ERROR]


def test_draft_snapshot_yields_warning() -> None:
    assert "core.snapshot.draft" in codes(make_project(), known_conductors={"AWG 18"})


def test_missing_core_is_info() -> None:
    issues = validate_project(make_project(core=None), known_conductors={"AWG 18"})
    issue = next(i for i in issues if i.code == "core.missing")
    assert issue.category is ValidationCategory.INFO


def test_manual_core_dimension_error() -> None:
    manual = ManualCoreSelection(0.010, 0.020, 0.005, 0.0)
    assert "core.manual.dimensions" in codes(make_project(core=manual))


def test_override_requires_reason_and_known_field() -> None:
    selection = CatalogCoreSelection(
        "0077071A7",
        make_core(),
        (
            CoreOverride("outer_diameter_m", 0.027, "  "),
            CoreOverride("bogus_field", 1.0, "why"),
        ),
    )
    result = codes(make_project(core=selection))
    assert {"core.override.reason", "core.override.field"} <= result


def test_winding_range_rules() -> None:
    bad = make_winding(turns=0, start_angle_deg=400.0, sector_deg=0.0, min_spacing_m=-1.0)
    result = codes(make_project(windings=(bad,)))
    assert {"winding.turns", "winding.start_angle", "winding.sector", "winding.spacing"} <= result


def test_excitation_rules() -> None:
    bad = make_winding(frequency_hz=0.0, dc_current_a=-1.0)
    assert "winding.excitation" in codes(make_project(windings=(bad,)))


def test_duplicate_ids() -> None:
    windings = (make_winding(winding_id="w1"), make_winding(winding_id="w1", start_angle_deg=200.0))
    assert "winding.id.duplicate" in codes(make_project(windings=windings))


def test_unknown_conductor_error_and_unchecked_info() -> None:
    project = make_project()
    assert "winding.conductor.unknown" in codes(project, known_conductors=set())
    issues = validate_project(project)
    info = next(i for i in issues if i.code == "winding.conductor.unchecked")
    assert info.category is ValidationCategory.INFO


def test_sector_overlap_detected_with_wraparound() -> None:
    windings = (
        make_winding(winding_id="w1", start_angle_deg=300.0, sector_deg=120.0),
        make_winding(winding_id="w2", start_angle_deg=30.0, sector_deg=60.0),
    )
    assert "winding.sector.overlap" in codes(make_project(windings=windings))


def test_adjacent_sectors_do_not_overlap() -> None:
    windings = (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=180.0),
        make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=180.0),
    )
    assert "winding.sector.overlap" not in codes(make_project(windings=windings))
