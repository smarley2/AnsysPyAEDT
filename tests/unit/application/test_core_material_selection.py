from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.core_material_selection import (
    ClearedSelection,
    apply_catalog_core,
    apply_manual_core,
    apply_material_revision,
    clear_material_selection,
    core_options,
    material_options,
    required_material_ref,
    revalidate_pinned_material,
)
from inductor_designer.application.services.material_selection import (
    MaterialSelectionError,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import MaterialRecord, MaterialStatus
from tests.fakes.material_repository import InMemoryMaterialRepository
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_catalog_records import make_core
from tests.unit.domain.test_project import make_material_record, make_project

# `make_material_record()` is Magnetics Kool Mu 60, which is exactly
# `make_core().material`, so the shipped fixtures are already a compatible pair.
# It carries no series and no sources, so `save(record, {})` passes the fake's
# sha256 check and `bh_series_id` must stay None.
OTHER_REF = MaterialRef("Magnetics", "High Flux", "60")


def repository_with(*records: MaterialRecord) -> InMemoryMaterialRepository:
    repository = InMemoryMaterialRepository()
    for record in records:
        repository.save(record, {})
    return repository


def test_catalog_core_declares_its_required_material() -> None:
    record = make_core()
    project = make_project(
        design=replace(
            make_project().design,
            core=CatalogCoreSelection(record.part_number, record, ()),
        )
    )

    assert required_material_ref(project) == record.material


def test_manual_core_requires_no_particular_material() -> None:
    project = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
        )
    )

    assert required_material_ref(project) is None


def test_core_options_filter_by_the_selected_material() -> None:
    record = make_core()

    assert [option.part_number for option in core_options(CATALOG, None)] == [
        record.part_number
    ]
    assert core_options(CATALOG, OTHER_REF) == ()
    assert len(core_options(CATALOG, record.material)) == 1


def test_material_options_list_only_selectable_revisions() -> None:
    approved = make_material_record()
    draft = replace(
        make_material_record(),
        revision_id="aaaaaaaaaaaa",
        status=MaterialStatus.DRAFT,
        reviewed_by=None,
        approved_by=None,
    )
    repository = repository_with(approved, draft)

    options = material_options(repository, None)

    assert [option.revision_id for option in options] == [approved.revision_id]
    assert options[0].bh_series_ids == ()


def test_material_options_filter_by_the_selected_core() -> None:
    approved = make_material_record()
    repository = repository_with(approved)

    assert material_options(repository, approved.ref) != ()
    assert material_options(repository, OTHER_REF) == ()


def test_selecting_an_incompatible_core_clears_the_material_and_explains() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project
    incompatible = replace(make_core(), material=OTHER_REF)

    class OneCore:
        def get_core(self, part_number: str) -> object:
            return incompatible if part_number == incompatible.part_number else None

        def list_cores(self) -> tuple[object, ...]:
            return (incompatible,)

        def get_conductor(self, name: str) -> None:
            return None

        def list_conductor_names(self) -> tuple[str, ...]:
            return ()

    outcome = apply_catalog_core(project, OneCore(), incompatible.part_number)  # type: ignore[arg-type]

    assert outcome.cleared is ClearedSelection.MATERIAL
    assert outcome.project.design.core_material is None
    assert isinstance(outcome.project.design.core, CatalogCoreSelection)
    assert OTHER_REF.name in outcome.message
    assert "cleared" in outcome.message


def test_selecting_an_incompatible_material_clears_the_core_and_explains() -> None:
    record = make_core()
    approved = replace(make_material_record(), ref=OTHER_REF)
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=CatalogCoreSelection(record.part_number, record, ()),
            core_material=None,
        )
    )

    outcome = apply_material_revision(
        project, repository, OTHER_REF, approved.revision_id, bh_series_id=None
    )

    assert outcome.cleared is ClearedSelection.CORE
    assert outcome.project.design.core is None
    assert outcome.project.design.core_material is not None
    assert record.part_number in outcome.message


def test_compatible_selection_clears_nothing() -> None:
    record = make_core()
    approved = make_material_record()
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=CatalogCoreSelection(record.part_number, record, ()),
            core_material=None,
        )
    )

    outcome = apply_material_revision(
        project, repository, approved.ref, approved.revision_id, bh_series_id=None
    )

    assert outcome.cleared is None
    assert outcome.project.design.core is not None
    assert outcome.project.design.core_material is not None
    assert outcome.project.design.manual_material_compatibility_acknowledged is False


def test_manual_core_material_requires_acknowledgment() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
            core_material=None,
        )
    )

    acknowledged = apply_material_revision(
        project,
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
        acknowledge_manual_compatibility=True,
    )

    assert acknowledged.project.design.manual_material_compatibility_acknowledged is True


def test_manual_core_dimensions_replace_the_core_without_touching_the_material() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project

    outcome = apply_manual_core(
        project,
        outer_diameter_m=0.0272,
        inner_diameter_m=0.0138,
        height_m=0.0112,
        corner_radius_m=0.0,
    )

    assert outcome.cleared is None
    assert isinstance(outcome.project.design.core, ManualCoreSelection)
    assert outcome.project.design.core_material is not None


def test_a_deleted_pinned_revision_becomes_unresolved_with_an_actionable_message() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project
    repository.delete_revision(approved.ref, approved.revision_id)

    outcome = revalidate_pinned_material(project, repository)

    assert outcome.cleared is ClearedSelection.MATERIAL
    assert outcome.project.design.core_material is None
    assert approved.revision_id in outcome.message
    assert "no longer" in outcome.message


def test_resizing_a_manual_core_drops_the_recorded_acknowledgement() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    manual = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
            core_material=None,
        )
    )
    pinned = apply_material_revision(
        manual,
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
        acknowledge_manual_compatibility=True,
    ).project
    assert pinned.design.manual_material_compatibility_acknowledged is True

    outcome = apply_manual_core(
        pinned,
        outer_diameter_m=0.030,
        inner_diameter_m=0.015,
        height_m=0.012,
        corner_radius_m=0.0,
    )

    assert outcome.project.design.manual_material_compatibility_acknowledged is False
    assert outcome.project.design.core_material is not None
    assert "Confirm material compatibility again" in outcome.message


def test_clearing_the_material_unpins_it_and_leaves_the_core() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project

    outcome = clear_material_selection(project)

    assert outcome.cleared is ClearedSelection.MATERIAL
    assert outcome.project.design.core_material is None
    assert outcome.project.design.core is not None
    assert (
        outcome.project.design.manual_material_compatibility_acknowledged is False
    )

    assert clear_material_selection(outcome.project).cleared is None


def test_a_still_present_pinned_revision_survives_a_library_refresh() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = apply_material_revision(
        make_project(design=replace(make_project().design, core=None, core_material=None)),
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
    ).project

    outcome = revalidate_pinned_material(project, repository)

    assert outcome.cleared is None
    assert outcome.project.design.core_material == project.design.core_material


def test_switching_from_a_manual_core_drops_the_acknowledgement() -> None:
    approved = make_material_record()
    repository = repository_with(approved)
    project = make_project(
        design=replace(
            make_project().design,
            core=ManualCoreSelection(0.0272, 0.0138, 0.0112, 0.0),
            core_material=None,
        )
    )
    acknowledged = apply_material_revision(
        project,
        repository,
        approved.ref,
        approved.revision_id,
        bh_series_id=None,
        acknowledge_manual_compatibility=True,
    ).project
    assert acknowledged.design.manual_material_compatibility_acknowledged is True

    # The catalog core is compatible with the pinned material, so nothing is
    # cleared -- but the acknowledgment still must not survive onto it.
    outcome = apply_catalog_core(acknowledged, CATALOG, make_core().part_number)

    assert outcome.cleared is None
    assert outcome.project.design.core_material is not None
    assert outcome.project.design.manual_material_compatibility_acknowledged is False


def test_an_unselectable_revision_is_refused_without_changing_the_project() -> None:
    draft = replace(
        make_material_record(),
        revision_id="aaaaaaaaaaaa",
        status=MaterialStatus.DRAFT,
        reviewed_by=None,
        approved_by=None,
    )
    repository = repository_with(draft)
    project = make_project(design=replace(make_project().design, core=None, core_material=None))

    with pytest.raises(MaterialSelectionError):
        apply_material_revision(
            project, repository, draft.ref, draft.revision_id, bh_series_id=None
        )
