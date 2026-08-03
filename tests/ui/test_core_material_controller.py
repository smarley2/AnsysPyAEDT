from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.application.services.core_material_selection import (  # noqa: E402
    apply_catalog_core,
    apply_material_revision,
)
from inductor_designer.domain.project import (  # noqa: E402
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef  # noqa: E402
from inductor_designer.materials.records import MaterialRecord  # noqa: E402
from inductor_designer.ui.core_material_controller import (  # noqa: E402
    CoreMaterialController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.fakes.material_repository import InMemoryMaterialRepository  # noqa: E402
from tests.unit.application.test_core_material_selection import (  # noqa: E402
    repository_with,
)
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_catalog_records import make_core  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project,
)

pytestmark = pytest.mark.ui


def build(
    project: InductorProject | None = None,
) -> tuple[ProjectSession, CoreMaterialController]:
    QGuiApplication.instance() or QGuiApplication([])
    repository = InMemoryMaterialRepository()
    record = make_material_record()
    repository.save(record, {})
    base = project if project is not None else make_project(
        design=replace(make_project().design, core=None, core_material=None)
    )
    session = ProjectSession(base)
    return session, CoreMaterialController(session, CATALOG, repository)


def test_both_lists_start_unfiltered() -> None:
    _, controller = build()

    assert [row["partNumber"] for row in controller.coreOptions] == [
        make_core().part_number
    ]
    assert [row["revisionId"] for row in controller.materialOptions] == [
        make_material_record().revision_id
    ]
    assert controller.selectedCore == {}
    assert controller.selectedMaterial == {}


def test_selecting_a_core_filters_the_material_list_and_publishes_the_project() -> None:
    session, controller = build()
    record = make_core()

    assert controller.selectCatalogCore(record.part_number) is True

    assert isinstance(session.project.design.core, CatalogCoreSelection)
    assert controller.selectedCore["partNumber"] == record.part_number
    assert all(
        row["manufacturer"] == record.material.manufacturer
        for row in controller.materialOptions
    )
    assert session.dirty is True


def test_selecting_a_material_filters_the_core_list() -> None:
    _, controller = build()
    record = make_material_record()

    assert (
        controller.selectMaterial(
            record.ref.manufacturer,
            record.ref.name,
            record.ref.grade,
            record.revision_id,
            "",
        )
        is True
    )

    assert controller.selectedMaterial["revisionId"] == record.revision_id
    assert [row["partNumber"] for row in controller.coreOptions] == [
        make_core().part_number
    ]


def test_a_manual_core_requires_and_records_acknowledgement() -> None:
    session, controller = build()
    record = make_material_record()

    assert controller.applyManualCore(27.2, 13.8, 11.2, 0.0) is True
    assert isinstance(session.project.design.core, ManualCoreSelection)
    assert session.project.design.core.outer_diameter_m == 0.0272
    assert controller.acknowledgementRequired is True
    assert controller.acknowledged is False

    assert controller.setAcknowledged(True) is True
    assert (
        controller.selectMaterial(
            record.ref.manufacturer,
            record.ref.name,
            record.ref.grade,
            record.revision_id,
            "",
        )
        is True
    )

    assert session.project.design.manual_material_compatibility_acknowledged is True


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


def test_a_catalog_core_needs_no_acknowledgement() -> None:
    _, controller = build()

    assert controller.selectCatalogCore(make_core().part_number) is True

    assert controller.acknowledgementRequired is False


def test_an_unselectable_revision_is_reported_not_raised() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    repository = InMemoryMaterialRepository()
    record = make_material_record()
    repository.save(record, {})
    session = ProjectSession(
        make_project(design=replace(make_project().design, core=None, core_material=None))
    )
    controller = CoreMaterialController(session, CATALOG, repository)

    assert (
        controller.selectMaterial(
            record.ref.manufacturer, record.ref.name, record.ref.grade, "missing", ""
        )
        is False
    )

    assert session.project.design.core_material is None
    assert "missing" in controller.message


def test_clearing_the_material_leaves_the_core_alone() -> None:
    session, controller = build()
    record = make_material_record()
    controller.selectCatalogCore(make_core().part_number)
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )

    assert controller.clearMaterial() is True

    assert session.project.design.core_material is None
    assert session.project.design.core is not None
    assert controller.selectedMaterial == {}


def test_a_library_refresh_keeps_a_still_valid_pinned_revision() -> None:
    session, controller = build()
    record = make_material_record()
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )
    pinned = session.project.design.core_material

    controller.refreshLibrary()

    assert session.project.design.core_material == pinned
    assert "unchanged" in controller.message


def test_a_library_refresh_unresolves_a_deleted_pinned_revision() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    repository = InMemoryMaterialRepository()
    record = make_material_record()
    repository.save(record, {})
    session = ProjectSession(
        make_project(design=replace(make_project().design, core=None, core_material=None))
    )
    controller = CoreMaterialController(session, CATALOG, repository)
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )
    repository.delete_revision(record.ref, record.revision_id)

    controller.refreshLibrary()

    assert session.project.design.core_material is None
    assert record.revision_id in controller.message
    assert controller.materialOptions == []


def test_a_blank_material_identity_is_refused_without_raising() -> None:
    """An unset ComboBox sends blanks; a slot must report, never raise."""
    _, controller = build()

    assert controller.selectMaterial("", "", "", "0123456789ab", "") is False

    assert "Unable to select material revision" in controller.message


def test_resizing_a_manual_core_drops_the_acknowledgement() -> None:
    session, controller = build()
    record = make_material_record()
    controller.applyManualCore(27.2, 13.8, 11.2, 0.0)
    controller.setAcknowledged(True)
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )
    assert session.project.design.manual_material_compatibility_acknowledged is True

    controller.applyManualCore(30.0, 15.0, 12.0, 0.0)

    assert controller.acknowledged is False
    # The project field is what exports and run manifests read.
    assert session.project.design.manual_material_compatibility_acknowledged is False
    assert "Confirm material compatibility again" in controller.message


def test_a_corrupt_material_library_is_reported_not_raised() -> None:
    """The overlay repository raises plain ValueError on a sha256 mismatch."""
    session, controller = build()
    record = make_material_record()
    controller.selectMaterial(
        record.ref.manufacturer,
        record.ref.name,
        record.ref.grade,
        record.revision_id,
        "",
    )

    class Corrupt:
        def list_materials(self) -> tuple[MaterialRef, ...]:
            return (record.ref,)

        def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]:
            return (record.revision_id,)

        def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord:
            raise ValueError("sha256 mismatch for source curve.csv")

    controller._materials = Corrupt()  # type: ignore[assignment]

    controller.refreshLibrary()

    assert "Unable to reload the material library" in controller.message
    assert "sha256 mismatch" in controller.message
    assert session.project.design.core_material is not None


def test_a_non_finite_manual_dimension_is_reported_not_raised() -> None:
    # Start from a project with an existing core (make_project()'s default
    # CatalogCoreSelection) so the assertion below proves a rejected NaN input
    # leaves prior state alone rather than trivially holding on an empty core.
    session, controller = build(make_project())

    assert controller.applyManualCore(float("nan"), 13.8, 11.2, 0.0) is False

    assert "Unable to apply manual core dimensions" in controller.message
    assert session.project.design.core is not None


def test_a_repository_io_error_during_selection_is_reported_not_raised() -> None:
    """`FileOverlayMaterialRepository` converts `FileNotFoundError` to
    `ValueError` but lets any other `OSError` through -- a `PermissionError`
    from a file locked by another process must not crash the slot.
    """
    session, controller = build()
    record = make_material_record()

    class LockedRepository:
        def list_materials(self) -> tuple[MaterialRef, ...]:
            return (record.ref,)

        def list_revisions(self, ref: MaterialRef) -> tuple[str, ...]:
            return (record.revision_id,)

        def get(self, ref: MaterialRef, revision_id: str) -> MaterialRecord:
            raise PermissionError("curve.csv is locked by another process")

    controller._materials = LockedRepository()  # type: ignore[assignment]

    assert (
        controller.selectMaterial(
            record.ref.manufacturer,
            record.ref.name,
            record.ref.grade,
            record.revision_id,
            "",
        )
        is False
    )

    assert "curve.csv is locked" in controller.message
    assert session.project.design.core_material is None


def test_clearing_the_core_resets_the_acknowledgement() -> None:
    """Finding 5 (M7c final review): `_publish` reset `_acknowledged` only on
    `ClearedSelection.MATERIAL`, not on `ClearedSelection.CORE`. Not reachable
    through today's UI (every route back to a Manual core goes through
    `applyManualCore`, which resets both), but the flag already caused one
    real defect, so the reset must hold on either kind of clear. Reached here
    through `selectMaterial`, which clears the CORE when a mismatched catalog
    core is present (`apply_material_revision`).
    """
    session, controller = build(make_project())  # ships with a CatalogCoreSelection
    other = replace(make_material_record(), ref=MaterialRef("Magnetics", "High Flux", "60"))
    repository = InMemoryMaterialRepository()
    repository.save(other, {})
    controller._materials = repository  # type: ignore[assignment]
    # Simulate a leftover acknowledgment flag: defence in depth, not reachable
    # through today's UI.
    controller._acknowledged = True

    assert (
        controller.selectMaterial(
            other.ref.manufacturer,
            other.ref.name,
            other.ref.grade,
            other.revision_id,
            "",
        )
        is True
    )

    assert session.project.design.core is None  # the mismatched core was cleared
    assert controller.acknowledged is False


def test_opening_material_studio_only_emits_a_request() -> None:
    _, controller = build()
    requests: list[int] = []
    controller.materialStudioRequested.connect(lambda: requests.append(1))

    controller.openMaterialStudio()

    assert requests == [1]
