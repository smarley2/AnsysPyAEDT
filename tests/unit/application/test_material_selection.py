from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.material_selection import (
    MaterialSelectionError,
    pin_material_revision,
)
from inductor_designer.domain.project import MaterialRevisionSelection
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialStatus, PointSeries, SeriesKind
from tests.unit.domain.test_project import (
    make_material_record,
    make_material_series,
    make_project,
    material_record_with_series,
)


@pytest.mark.parametrize("status", [MaterialStatus.DRAFT, MaterialStatus.REVIEWED])
def test_pin_material_revision_requires_imported_or_approved_record(status: MaterialStatus) -> None:
    record = make_material_record()
    record = replace(
        record,
        status=status,
        reviewed_by="reviewer@example.com" if status is MaterialStatus.REVIEWED else None,
        approved_by=None,
    )

    with pytest.raises(MaterialSelectionError) as captured:
        pin_material_revision(make_project(), record, bh_series_id=None)

    assert captured.value.issues == (
        "Material revision must be imported or approved before project selection.",
    )


def test_pin_material_revision_accepts_imported_record() -> None:
    record = replace(
        make_material_record(),
        status=MaterialStatus.IMPORTED,
        reviewed_by=None,
        approved_by=None,
    )

    updated = pin_material_revision(make_project(), record, bh_series_id=None)

    assert updated.design.core_material is not None
    assert updated.design.core_material.snapshot is record


@pytest.mark.parametrize(
    "series",
    [(), (make_material_series(),)],
)
def test_pin_material_revision_allows_null_for_zero_or_one_bh_series(
    series: tuple[PointSeries, ...],
) -> None:
    record = material_record_with_series(*series) if series else make_material_record()

    updated = pin_material_revision(make_project(), record, bh_series_id=None)

    assert updated.design.core_material is not None
    assert updated.design.core_material.snapshot is record


def test_pin_material_revision_requires_explicit_id_for_multiple_bh_series() -> None:
    record = material_record_with_series(
        make_material_series("bh-25c"),
        make_material_series("bh-100c"),
    )

    with pytest.raises(MaterialSelectionError) as captured:
        pin_material_revision(make_project(), record, bh_series_id=None)

    assert captured.value.issues == (
        "Material revision contains multiple B-H series; select one explicitly.",
    )


@pytest.mark.parametrize(
    ("bh_series_id", "message"),
    [
        ("", "B-H series ID cannot be blank."),
        ("missing", "B-H series 'missing' does not exist in the material revision."),
        ("loss-100khz", "Series 'loss-100khz' is not a B-H curve."),
    ],
)
def test_pin_material_revision_rejects_invalid_explicit_id(
    bh_series_id: str,
    message: str,
) -> None:
    record = material_record_with_series(
        make_material_series("bh-25c"),
        make_material_series("loss-100khz", SeriesKind.LOSS_TABLE),
    )

    with pytest.raises(MaterialSelectionError) as captured:
        pin_material_revision(
            make_project(),
            record,
            bh_series_id=bh_series_id,
        )

    assert captured.value.issues == (message,)


def test_pin_material_revision_rejects_validation_errors() -> None:
    record = replace(make_material_record(), relative_permeability=0.5)

    with pytest.raises(MaterialSelectionError) as captured:
        pin_material_revision(make_project(), record, bh_series_id=None)

    assert captured.value.issues == (
        "relative permeability must be between 1 and 1e6",
    )


def test_pin_material_revision_preserves_explicit_id_and_exact_snapshot() -> None:
    selected = material_record_with_series(
        make_material_series("bh-25c"),
        make_material_series("bh-100c"),
    )
    newer_but_unselected = replace(selected, revision_id="abcdef012345")

    updated = pin_material_revision(
        make_project(),
        selected,
        bh_series_id="bh-100c",
    )

    assert newer_but_unselected.revision_id != selected.revision_id
    assert updated.design.core_material is not None
    assert updated.design.core_material.snapshot is selected
    assert updated.design.core_material.bh_series_id == "bh-100c"


def test_pin_material_revision_replaces_the_previous_single_selection() -> None:
    selected = material_record_with_series(make_material_series())
    previous = replace(selected, revision_id="aaaaaaaaaaaa")
    project = make_project(
        design=replace(
            make_project().design,
            core_material=MaterialRevisionSelection(previous.ref, previous.revision_id, previous),
        )
    )

    updated = pin_material_revision(project, selected, bh_series_id=None)

    assert updated.design.core_material is not None
    assert updated.design.core_material.snapshot is selected
    assert updated is not project
    assert project.design.core_material is not None
    assert project.design.core_material.snapshot is previous


def test_pin_material_revision_rejects_catalog_identity_mismatch() -> None:
    record = replace(
        make_material_record(),
        ref=MaterialRef("Magnetics", "Kool Mu", "75"),
    )

    with pytest.raises(MaterialSelectionError, match="does not match"):
        pin_material_revision(make_project(), record, bh_series_id=None)


def test_pin_material_revision_sets_manual_acknowledgment_only_from_argument() -> None:
    updated = pin_material_revision(
        make_project(),
        make_material_record(),
        bh_series_id=None,
        manual_compatibility_acknowledged=True,
    )

    assert updated.design.manual_material_compatibility_acknowledged is True
