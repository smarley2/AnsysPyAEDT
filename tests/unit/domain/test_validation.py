from __future__ import annotations

from dataclasses import replace

from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    Design,
    ManualCoreSelection,
    MaterialRevisionSelection,
    WindingOperatingPoint,
)
from inductor_designer.domain.validation import ValidationCategory, validate_project
from inductor_designer.domain.winding import CurrentDirection
from inductor_designer.materials.identity import MaterialRef
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import (
    make_material_record,
    make_operating_point,
    make_project,
    make_winding,
)


def codes(project: object, **kwargs: object) -> set[str]:
    return {issue.code for issue in validate_project(project, **kwargs)}  # type: ignore[arg-type]


def test_valid_project_has_no_errors() -> None:
    windings = (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=150.0),
        make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=150.0),
    )
    project = make_project(
        design=replace(make_project().design, windings=windings),
        operating_point=make_operating_point(
            WindingOperatingPoint("w1", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
            WindingOperatingPoint("w2", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
        )
    )
    issues = validate_project(project, known_conductors={"AWG 18"})
    assert not [i for i in issues if i.category is ValidationCategory.ERROR]


def test_draft_snapshot_yields_warning() -> None:
    assert "core.snapshot.draft" in codes(make_project(), known_conductors={"AWG 18"})


def test_missing_core_is_info() -> None:
    project = make_project(design=replace(make_project().design, core=None))
    issues = validate_project(project, known_conductors={"AWG 18"})
    issue = next(i for i in issues if i.code == "core.missing")
    assert issue.category is ValidationCategory.INFO


def test_manual_core_dimension_error() -> None:
    manual = ManualCoreSelection(0.010, 0.020, 0.005, 0.0)
    assert "core.manual.dimensions" in codes(
        make_project(design=replace(make_project().design, core=manual))
    )


def test_override_requires_reason_and_known_field() -> None:
    selection = CatalogCoreSelection(
        "0077071A7",
        make_core(),
        (
            CoreOverride("outer_diameter_m", 0.027, "  "),
            CoreOverride("bogus_field", 1.0, "why"),
        ),
    )
    result = codes(make_project(design=replace(make_project().design, core=selection)))
    assert {"core.override.reason", "core.override.field"} <= result


def test_winding_range_rules() -> None:
    bad = make_winding(turns=0, start_angle_deg=400.0, sector_deg=0.0, min_spacing_m=-1.0)
    result = codes(make_project(design=replace(make_project().design, windings=(bad,))))
    assert {"winding.turns", "winding.start_angle", "winding.sector", "winding.spacing"} <= result


def test_missing_operating_point_entry_has_exact_code_and_path() -> None:
    windings = (make_winding(winding_id="w1"), make_winding(winding_id="w2"))
    project = make_project(design=replace(make_project().design, windings=windings))
    issue = next(
        item
        for item in validate_project(project)
        if item.code == "operating-point.winding.missing"
    )
    assert issue.path == "operatingPoint.windings"
    assert issue.category is ValidationCategory.ERROR


def test_unknown_operating_point_entry_has_exact_code_and_path() -> None:
    project = make_project(
        operating_point=make_operating_point(
            WindingOperatingPoint("unknown", 2.0, 0.0, 5.0, CurrentDirection.FORWARD)
        )
    )
    issue = next(
        item
        for item in validate_project(project)
        if item.code == "operating-point.winding.unknown"
    )
    assert issue.path == "operatingPoint.windings[0]"
    assert issue.category is ValidationCategory.ERROR


def test_duplicate_operating_point_entry_has_exact_code_and_path() -> None:
    project = make_project(
        operating_point=make_operating_point(
            WindingOperatingPoint("w1", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
            WindingOperatingPoint("w1", 2.0, 0.0, 5.0, CurrentDirection.FORWARD),
        )
    )
    issue = next(
        item
        for item in validate_project(project)
        if item.code == "operating-point.winding.duplicate"
    )
    assert issue.path == "operatingPoint.windings[1]"
    assert issue.category is ValidationCategory.ERROR


def test_duplicate_ids() -> None:
    windings = (make_winding(winding_id="w1"), make_winding(winding_id="w1", start_angle_deg=200.0))
    project = make_project(design=replace(make_project().design, windings=windings))
    assert "winding.id.duplicate" in codes(project)


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
    project = make_project(design=replace(make_project().design, windings=windings))
    assert "winding.sector.overlap" in codes(project)


def test_adjacent_sectors_do_not_overlap() -> None:
    windings = (
        make_winding(winding_id="w1", start_angle_deg=0.0, sector_deg=180.0),
        make_winding(winding_id="w2", start_angle_deg=180.0, sector_deg=180.0),
    )
    project = make_project(design=replace(make_project().design, windings=windings))
    assert "winding.sector.overlap" not in codes(project)


def test_catalog_core_and_material_identity_mismatch_has_exact_code_and_path() -> None:
    mismatched = replace(
        make_material_record(),
        ref=MaterialRef("Magnetics", "Kool Mu", "75"),
    )
    selection = MaterialRevisionSelection(mismatched.ref, mismatched.revision_id, mismatched)
    project = make_project(
        design=replace(make_project().design, core_material=selection)
    )
    issue = next(
        item for item in validate_project(project) if item.code == "core-material.incompatible"
    )
    assert issue.path == "design.coreMaterial"
    assert issue.category is ValidationCategory.ERROR


def test_manual_core_and_material_without_acknowledgment_has_exact_code_and_path() -> None:
    record = make_material_record()
    selection = MaterialRevisionSelection(record.ref, record.revision_id, record)
    design = Design(
        ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0),
        (make_winding(),),
        selection,
        False,
    )
    issue = next(
        item
        for item in validate_project(make_project(design=design))
        if item.code == "core-material.manual-unacknowledged"
    )
    assert issue.path == "design.manualMaterialCompatibilityAcknowledged"
    assert issue.category is ValidationCategory.ERROR


def test_unused_manual_acknowledgment_is_info_with_exact_path() -> None:
    project = make_project(
        design=replace(
            make_project().design,
            manual_material_compatibility_acknowledged=True,
        )
    )
    issue = next(
        item
        for item in validate_project(project)
        if item.code == "core-material.acknowledgment-unused"
    )
    assert issue.path == "design.manualMaterialCompatibilityAcknowledged"
    assert issue.category is ValidationCategory.INFO
