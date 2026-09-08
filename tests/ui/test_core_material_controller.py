from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

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


def _filled_core_csv(part_numbers: tuple[str, ...]) -> bytes:
    """A template filled the way a user fills it: one row per part number."""
    import csv
    import io

    from inductor_designer.adapters.catalog.core_table import CORE_TEMPLATE_COLUMNS

    values = {
        "manufacturer": "BRUSA",
        "family": "powder-toroid",
        "materialManufacturer": "Magnetics",
        "materialName": "Kool Mu",
        "materialGrade": "60",
        "coating": "parylene",
        "catalogRevision": "brusa-lab-2026",
        "sourceUrl": "https://example.invalid/datasheet.pdf",
        "sourcePage": "4",
        "outerDiameterNominalM": "0.0267",
        "innerDiameterNominalM": "0.0147",
        "heightNominalM": "0.0112",
        "effectiveAreaM2": "6.55e-5",
        "pathLengthM": "0.0635",
        "volumeM3": "4.16e-6",
        "alValueNh": "75.0",
        "reviewStatus": "draft",
    }
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CORE_TEMPLATE_COLUMNS))
    writer.writeheader()
    for part_number in part_numbers:
        writer.writerow({**{name: "" for name in CORE_TEMPLATE_COLUMNS},
                         **values, "partNumber": part_number})
    return buffer.getvalue().encode("utf-8")


def test_importing_cores_offers_them_and_stores_them_outside_the_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the storage location: an upgrade rewrites the
    installed bundle, so an imported core written there is on a countdown.
    Asserted against both paths, not just the happy one."""
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())
    before = len(controller.coreOptions)

    source = tmp_path / "two-cores.csv"
    source.write_bytes(_filled_core_csv(("BRUSA-A", "BRUSA-B")))
    assert controller.importCores(source.as_uri()) is True

    parts = {row["partNumber"]: row for row in controller.coreOptions}
    assert len(controller.coreOptions) == before + 2
    assert parts["BRUSA-A"]["origin"] == "imported"
    assert parts["BRUSA-A"]["reviewStatus"] == "draft"
    assert "2" in controller.message and "0" in controller.message

    # Two files, under the per-user data directory -- the filenames are
    # sanitized (`BRUSA-A` -> `BRUSA_A.json`), so the part number is the one
    # inside the record, which `coreOptions` above already read back.
    written = catalog_overlay_directory() / "cores"
    assert len(list(written.glob("*.json"))) == 2
    assert catalog_overlay_directory().is_relative_to(tmp_path / "data")


def test_importing_a_core_the_catalog_already_ships_is_refused_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shadowing a shipped part would make Review cite a part number whose
    numbers are someone's edit."""
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    shipped = CATALOG.list_cores()[0].part_number
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())

    source = tmp_path / "clash.csv"
    source.write_bytes(_filled_core_csv((shipped,)))
    assert controller.importCores(source.as_uri()) is False

    assert shipped in controller.message
    assert not (catalog_overlay_directory() / "cores").exists()


def test_the_core_template_downloads_with_its_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, CATALOG, InMemoryMaterialRepository())

    target = tmp_path / "template.csv"
    assert controller.downloadCoreTemplate("csv", target.as_uri()) is True
    assert target.read_text(encoding="utf-8").startswith("manufacturer,family,partNumber")


def test_marking_an_imported_core_reviewed_records_the_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The status only means something if a person is attached to it, so the
    slot takes a name and the row shows the promotion."""
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())
    source = tmp_path / "one.csv"
    source.write_bytes(_filled_core_csv(("BRUSA-A",)))
    assert controller.importCores(source.as_uri()) is True

    assert controller.markCoreReviewed("BRUSA-A", "F. Posser") is True

    row = next(r for r in controller.coreOptions if r["partNumber"] == "BRUSA-A")
    assert row["reviewStatus"] == "reviewed"
    assert "F. Posser" in controller.message


def test_marking_a_core_reviewed_without_a_name_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())
    source = tmp_path / "one.csv"
    source.write_bytes(_filled_core_csv(("BRUSA-A",)))
    controller.importCores(source.as_uri())

    assert controller.markCoreReviewed("BRUSA-A", "  ") is False

    row = next(r for r in controller.coreOptions if r["partNumber"] == "BRUSA-A")
    assert row["reviewStatus"] == "draft"


def test_a_shipped_core_cannot_be_marked_reviewed_from_the_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shipped core's status belongs to the repository's catalog source and
    its review process, not to whoever has the application open."""
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    shipped = CATALOG.list_cores()[0].part_number
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())

    assert controller.markCoreReviewed(shipped, "F. Posser") is False
    assert shipped in controller.message


def test_the_selected_core_carries_the_provenance_the_list_shows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen offers "mark reviewed" only for an imported draft, so the
    selection has to say which it is -- otherwise the control would appear for
    a shipped core it cannot promote."""
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())
    source = tmp_path / "one.csv"
    source.write_bytes(_filled_core_csv(("BRUSA-A",)))
    controller.importCores(source.as_uri())

    assert controller.selectCatalogCore("BRUSA-A") is True
    assert controller.selectedCore["origin"] == "imported"
    assert controller.selectedCore["reviewStatus"] == "draft"

    controller.markCoreReviewed("BRUSA-A", "F. Posser")
    assert controller.selectedCore["reviewStatus"] == "reviewed"

    shipped = CATALOG.list_cores()[0].part_number
    controller.selectCatalogCore(shipped)
    assert controller.selectedCore["origin"] == "shipped"


def test_promoting_a_core_leaves_the_project_snapshot_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project records the numbers it was designed against, so marking the
    catalog record reviewed must not rewrite the pinned snapshot -- only the
    reported status follows the catalog."""
    from inductor_designer.adapters.catalog.overlay_repository import (
        OverlayCatalogRepository,
    )
    from inductor_designer.adapters.system.environment import catalog_overlay_directory
    from inductor_designer.domain.catalog_records import ReviewStatus

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    QGuiApplication.instance() or QGuiApplication([])
    catalog = OverlayCatalogRepository(CATALOG, catalog_overlay_directory())
    session = ProjectSession(make_project())
    controller = CoreMaterialController(session, catalog, InMemoryMaterialRepository())
    source = tmp_path / "one.csv"
    source.write_bytes(_filled_core_csv(("BRUSA-A",)))
    controller.importCores(source.as_uri())
    controller.selectCatalogCore("BRUSA-A")

    controller.markCoreReviewed("BRUSA-A", "F. Posser")

    pinned = session.project.design.core
    assert isinstance(pinned, CatalogCoreSelection)
    assert pinned.snapshot.review_status is ReviewStatus.DRAFT
    assert controller.selectedCore["reviewStatus"] == "reviewed"


# --- Manual gapped E core (M11a task 8) -----------------------------------


def _ecore_controller() -> tuple[ProjectSession, CoreMaterialController]:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project())
    return session, CoreMaterialController(
        session, CATALOG, InMemoryMaterialRepository()
    )


def test_applying_a_manual_e_core_selects_it_with_its_gap_stack() -> None:
    """Millimetres in, metres stored -- the same boundary the manual toroid
    fields already cross, so a user never types a number in metres."""
    from inductor_designer.domain.project import ManualECoreSelection

    session, controller = _ecore_controller()

    assert (
        controller.applyManualECore(17.0, 21.0, 9.2, 18.7, 8.5, 9.3, "0.5, 0.5", "4", False)
        is True
    )

    core = session.project.design.core
    assert isinstance(core, ManualECoreSelection)
    assert core.centre_leg_width_m == pytest.approx(0.017)
    assert core.window_height_m == pytest.approx(0.0187)
    assert core.gaps_m == (pytest.approx(0.0005), pytest.approx(0.0005))
    assert core.gap_spacings_m == (pytest.approx(0.004),)
    assert core.outer_legs_gapped is False


def test_an_ungapped_e_core_takes_an_empty_gap_list() -> None:
    from inductor_designer.domain.project import ManualECoreSelection

    session, controller = _ecore_controller()

    assert controller.applyManualECore(17.0, 21.0, 9.2, 18.7, 8.5, 9.3, "", "", True) is True

    core = session.project.design.core
    assert isinstance(core, ManualECoreSelection)
    assert core.gaps_m == ()
    assert core.outer_legs_gapped is True


def test_a_gap_list_that_is_not_numbers_is_refused_and_changes_nothing() -> None:
    """A typed field is where a NaN gets in, so the refusal names the text
    rather than storing a gap nobody can grind."""
    session, controller = _ecore_controller()
    before = session.project.design.core

    applied = controller.applyManualECore(
        17.0, 21.0, 9.2, 18.7, 8.5, 9.3, "0.5, x", "", False
    )
    assert applied is False

    assert session.project.design.core == before
    assert "gap" in controller.message.lower()


def test_a_gap_stack_that_does_not_fit_the_leg_is_refused_with_the_reason() -> None:
    """The body's own rule, surfaced where the user typed it: two 20 mm gaps
    cannot be ground into a 37.4 mm leg with a segment between them."""
    session, controller = _ecore_controller()

    assert (
        controller.applyManualECore(17.0, 21.0, 9.2, 18.7, 8.5, 9.3, "20, 20", "1", False)
        is False
    )
    assert "centre leg" in controller.message


def test_the_wrong_number_of_gap_spacings_is_refused() -> None:
    session, controller = _ecore_controller()

    assert (
        controller.applyManualECore(17.0, 21.0, 9.2, 18.7, 8.5, 9.3, "0.5, 0.5, 0.5", "4", False)
        is False
    )
    assert "spacing" in controller.message
