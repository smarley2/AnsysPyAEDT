"""The `Core & Material` screen (specification section 4.1).

The controller owns no rules: it converts the session project into QML rows and
routes every change through `core_material_selection`, so the filtering and the
never-substituting clear stay testable without Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot

from inductor_designer.application.services.core_material_selection import (
    ClearedSelection,
    SelectionOutcome,
    apply_catalog_core,
    apply_manual_core,
    apply_manual_ecore,
    apply_material_revision,
    clear_material_selection,
    core_options,
    material_options,
    required_material_ref,
    revalidate_pinned_material,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.materials.identity import MaterialRef

if TYPE_CHECKING:
    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.application.ports.material_repository import (
        MaterialRepository,
    )
    from inductor_designer.ui.project_session import ProjectSession


class CoreMaterialController(QObject):
    optionsChanged = Signal()
    selectionChanged = Signal()
    messageChanged = Signal()
    materialStudioRequested = Signal()

    def __init__(
        self,
        session: ProjectSession,
        catalog: CatalogRepository,
        materials: MaterialRepository,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._catalog = catalog
        self._materials = materials
        self._message = ""
        self._acknowledged = (
            session.project.design.manual_material_compatibility_acknowledged
        )

    def _overlay_part_numbers(self) -> tuple[str, ...]:
        """Which offered cores came from the user's own overlay, if any.

        Asked of the repository by duck typing rather than by importing the
        overlay adapter: this controller is handed whatever satisfies the
        catalog port, and a plain SQLite repository (every unit test, and a
        launch before the first import) simply has no overlay to report.
        """
        reader = getattr(self._catalog, "overlay_part_numbers", None)
        return tuple(reader()) if callable(reader) else ()

    def _get_core_options(self) -> list[dict[str, object]]:
        pinned = self._session.project.design.core_material
        options = core_options(
            self._catalog,
            pinned.ref if pinned else None,
            overlay_part_numbers=self._overlay_part_numbers(),
        )
        return [
            {
                "partNumber": option.part_number,
                "manufacturer": option.manufacturer,
                "family": option.family.value,
                "materialLabel": (
                    f"{option.material_ref.manufacturer} {option.material_ref.name} "
                    f"{option.material_ref.grade}"
                ),
                "outerDiameterMm": option.outer_diameter_m * 1000.0,
                "innerDiameterMm": option.inner_diameter_m * 1000.0,
                "heightMm": option.height_m * 1000.0,
                # Provenance, on every row: a `draft` core is a transcription
                # nobody has checked against the cited source page, and an
                # imported one is a datasheet the user typed in themselves.
                "reviewStatus": option.review_status.value,
                "origin": option.origin.value,
            }
            for option in options
        ]

    coreOptions = Property(list, _get_core_options, notify=optionsChanged)

    def _get_material_options(self) -> list[dict[str, object]]:
        options = material_options(
            self._materials, required_material_ref(self._session.project)
        )
        return [
            {
                "manufacturer": option.ref.manufacturer,
                "name": option.ref.name,
                "grade": option.ref.grade,
                "revisionId": option.revision_id,
                "status": option.status.value,
                "createdAt": option.created_at,
                "bhSeriesIds": list(option.bh_series_ids),
            }
            for option in options
        ]

    materialOptions = Property(list, _get_material_options, notify=optionsChanged)

    def _get_selected_core(self) -> dict[str, object]:
        core = self._session.project.design.core
        if isinstance(core, CatalogCoreSelection):
            return {
                "kind": "catalog",
                # Read from the catalog, not from the snapshot the project
                # pinned when this core was selected: "has this data been
                # checked?" is a question about the record as it stands now,
                # and marking a core reviewed must not appear to do nothing.
                # The pinned snapshot itself is deliberately left alone --
                # a project records the numbers it was designed against.
                "reviewStatus": (
                    current.review_status.value
                    if (current := self._catalog.get_core(core.part_number))
                    is not None
                    else core.snapshot.review_status.value
                ),
                "origin": (
                    "imported"
                    if core.part_number in self._overlay_part_numbers()
                    else "shipped"
                ),
                "partNumber": core.part_number,
                "manufacturer": core.snapshot.manufacturer,
                "materialLabel": (
                    f"{core.snapshot.material.manufacturer} "
                    f"{core.snapshot.material.name} {core.snapshot.material.grade}"
                ),
                "outerDiameterMm": core.snapshot.outer_diameter.nominal_m * 1000.0,
                "innerDiameterMm": core.snapshot.inner_diameter.nominal_m * 1000.0,
                "heightMm": core.snapshot.height.nominal_m * 1000.0,
                "pathLengthMm": core.snapshot.path_length_m * 1000.0,
            }
        if isinstance(core, ManualCoreSelection):
            return {
                "kind": "manual",
                "outerDiameterMm": core.outer_diameter_m * 1000.0,
                "innerDiameterMm": core.inner_diameter_m * 1000.0,
                "heightMm": core.height_m * 1000.0,
                "cornerRadiusMm": core.corner_radius_m * 1000.0,
            }
        return {}

    selectedCore = Property(dict, _get_selected_core, notify=selectionChanged)

    def _get_selected_material(self) -> dict[str, object]:
        material = self._session.project.design.core_material
        if material is None:
            return {}
        return {
            "manufacturer": material.ref.manufacturer,
            "name": material.ref.name,
            "grade": material.ref.grade,
            "revisionId": material.revision_id,
            "status": material.snapshot.status.value,
            "bhSeriesId": material.bh_series_id or "",
        }

    selectedMaterial = Property(dict, _get_selected_material, notify=selectionChanged)

    def _get_acknowledgement_required(self) -> bool:
        return isinstance(self._session.project.design.core, ManualCoreSelection)

    acknowledgementRequired = Property(
        bool, _get_acknowledgement_required, notify=selectionChanged
    )

    def _get_acknowledged(self) -> bool:
        return self._acknowledged

    acknowledged = Property(bool, _get_acknowledged, notify=selectionChanged)

    def _get_message(self) -> str:
        return self._message

    message = Property(str, _get_message, notify=messageChanged)

    def _set_message(self, message: str) -> None:
        self._message = message
        self.messageChanged.emit()

    def _publish(self, outcome: SelectionOutcome) -> bool:
        self._session.apply(outcome.project)
        self._session.set_status(outcome.message)
        if outcome.cleared in (ClearedSelection.MATERIAL, ClearedSelection.CORE):
            self._acknowledged = False
        self._set_message(outcome.message)
        self.optionsChanged.emit()
        self.selectionChanged.emit()
        return True

    @Slot(str, result=bool)
    def selectCatalogCore(self, part_number: str) -> bool:
        try:
            outcome = apply_catalog_core(
                self._session.project, self._catalog, part_number
            )
        except Exception as error:  # noqa: BLE001 - a QML slot must never raise
            # The catalog is a SQLite file: a locked or corrupt index raises
            # from the driver, not as a LookupError.
            self._set_message(f"Unable to select core: {error}")
            return False
        self._acknowledged = False
        return self._publish(outcome)

    @Slot(float, float, float, float, result=bool)
    def applyManualCore(
        self,
        outer_diameter_mm: float,
        inner_diameter_mm: float,
        height_mm: float,
        corner_radius_mm: float,
    ) -> bool:
        # New dimensions are new geometry, so a compatibility attestation the
        # user made about the previous shape must not carry over.
        self._acknowledged = False
        try:
            outcome = apply_manual_core(
                self._session.project,
                outer_diameter_m=outer_diameter_mm / 1000.0,
                inner_diameter_m=inner_diameter_mm / 1000.0,
                height_m=height_mm / 1000.0,
                corner_radius_m=corner_radius_mm / 1000.0,
            )
        except ValueError as error:
            # `ManualCoreSelection` refuses non-finite and non-positive
            # dimensions, and QML `Number("")` yields NaN.
            self._set_message(f"Unable to apply manual core dimensions: {error}")
            return False
        return self._publish(outcome)

    @staticmethod
    def _lengths_mm(text: str, label: str) -> tuple[float, ...]:
        """A comma-separated list of millimetre lengths, as metres.

        A typed field is where a NaN gets in, so this refuses the text rather
        than passing `float("nan")` into a core nobody could grind.
        """
        entries = [part.strip() for part in text.split(",") if part.strip()]
        values: list[float] = []
        for entry in entries:
            try:
                values.append(float(entry) / 1000.0)
            except ValueError as error:
                raise ValueError(f"{label} must be numbers in mm, got {entry!r}") from error
        return tuple(values)

    @Slot(float, float, float, float, float, float, str, str, bool, result=bool)
    def applyManualECore(
        self,
        centre_leg_width_mm: float,
        depth_mm: float,
        window_width_mm: float,
        window_height_mm: float,
        outer_leg_width_mm: float,
        yoke_thickness_mm: float,
        gaps_mm: str,
        gap_spacings_mm: str,
        outer_legs_gapped: bool,
    ) -> bool:
        """Select a manual gapped E core from the entered dimensions.

        Gaps arrive as text because there can be several of them; every other
        field is a number, and all of them are millimetres in, metres stored --
        the same boundary the manual toroid fields already cross, so a user
        never types a number in metres.
        """
        # New dimensions are new geometry, so a compatibility attestation the
        # user made about the previous shape must not carry over.
        self._acknowledged = False
        try:
            outcome = apply_manual_ecore(
                self._session.project,
                centre_leg_width_m=centre_leg_width_mm / 1000.0,
                depth_m=depth_mm / 1000.0,
                window_width_m=window_width_mm / 1000.0,
                window_height_m=window_height_mm / 1000.0,
                outer_leg_width_m=outer_leg_width_mm / 1000.0,
                yoke_thickness_m=yoke_thickness_mm / 1000.0,
                gaps_m=self._lengths_mm(gaps_mm, "Gap lengths"),
                gap_spacings_m=self._lengths_mm(gap_spacings_mm, "Gap spacings"),
                outer_legs_gapped=outer_legs_gapped,
            )
        except ValueError as error:
            # `FinishedECore` refuses a stack that does not fit the leg and a
            # spacing count that does not separate the gaps; `ManualECoreSelection`
            # refuses non-finite dimensions, and QML `Number("")` yields NaN.
            self._set_message(f"Unable to apply manual E-core dimensions: {error}")
            return False
        return self._publish(outcome)

    @Slot(str, str, str, str, str, result=bool)
    def selectMaterial(
        self,
        manufacturer: str,
        name: str,
        grade: str,
        revision_id: str,
        bh_series_id: str,
    ) -> bool:
        try:
            # MaterialRef refuses a blank field, and an unset ComboBox sends
            # blanks: construct it inside the guard so no slot ever raises.
            ref = MaterialRef(manufacturer, name, grade)
            outcome = apply_material_revision(
                self._session.project,
                self._materials,
                ref,
                revision_id,
                bh_series_id=bh_series_id.strip() or None,
                acknowledge_manual_compatibility=self._acknowledged,
            )
        except (KeyError, ValueError, OSError) as error:
            # KeyError covers MaterialLookupError, ValueError a blank identity
            # or MaterialSelectionError (which subclasses it), and OSError a
            # repository I/O failure (e.g. a revision file locked by another
            # process); a missing or unselectable revision is reported, never
            # auto-substituted.
            issues = getattr(error, "issues", None)
            detail = "; ".join(issues) if issues else str(error)
            self._set_message(
                f"Unable to select material revision {revision_id}: {detail}"
            )
            return False
        return self._publish(outcome)

    @Slot(result=bool)
    def clearMaterial(self) -> bool:
        outcome = clear_material_selection(self._session.project)
        if outcome.cleared is None:
            self._set_message(outcome.message)
            return False
        self._acknowledged = False
        return self._publish(outcome)

    @Slot(bool, result=bool)
    def setAcknowledged(self, acknowledged: bool) -> bool:
        """Record the Manual-core compatibility assumption before it is used.

        The value only reaches the project when a material is pinned, because
        `Design.manual_material_compatibility_acknowledged` describes exactly
        that pairing.
        """
        self._acknowledged = acknowledged
        self.selectionChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def downloadCoreTemplate(self, file_format: str, destination_url: str) -> bool:
        """Write an empty core table for the user to fill in from a datasheet.

        Same shape as Material Studio's `downloadTemplate`, deliberately: the
        two import flows should not be two different habits to learn.
        """
        from inductor_designer.adapters.catalog.core_table import core_import_template

        try:
            template = core_import_template(file_format)
            destination = Path(QUrl(destination_url).toLocalFile())
            destination.write_bytes(template.data)
        except (OSError, ValueError) as error:
            self._set_message(f"Unable to save the core template: {error}")
            return False
        self._set_message(
            f"Core template saved to {destination.name}. Fill one row per part "
            "number, then use Import cores."
        )
        return True

    @Slot(str, result=bool)
    def importCores(self, source_url: str) -> bool:
        """Read a filled core table and add every row that stands on its own.

        Returns False when nothing was imported, so the caller can tell "your
        file had problems" from "your cores are in". Both cases report what
        happened per row: a datasheet family is ten rows off one page, and the
        user needs to know which one to go and fix.
        """
        from inductor_designer.adapters.catalog.core_table import (
            CoreTableError,
            import_core_file,
        )
        from inductor_designer.adapters.catalog.overlay_repository import (
            CoreOverlayError,
            write_overlay_core,
        )
        from inductor_designer.adapters.system.environment import (
            catalog_overlay_directory,
        )

        source = Path(QUrl(source_url).toLocalFile())
        try:
            result = import_core_file(source.name, source.read_bytes())
        except (OSError, CoreTableError) as error:
            self._set_message(f"Unable to import cores: {error}")
            return False

        overlay_root = catalog_overlay_directory()
        imported = 0
        problems = [
            f"row {rejection.row}: {rejection.reason}" for rejection in result.rejections
        ]
        for record in result.records:
            try:
                write_overlay_core(overlay_root, record, shipped=self._catalog)
            except (OSError, CoreOverlayError) as error:
                problems.append(f"{record.part_number}: {error}")
                continue
            imported += 1

        self.optionsChanged.emit()
        summary = f"Imported {imported} core(s); {len(problems)} refused."
        if problems:
            # Every refusal, not a count: the user has to fix each one, and a
            # count tells them only that something is wrong somewhere.
            summary = summary + " " + " | ".join(problems)
        self._set_message(summary)
        return imported > 0

    @Slot(str, str, result=bool)
    def markCoreReviewed(self, part_number: str, reviewed_by: str) -> bool:
        """Record that a person checked one of your imported cores.

        `catalog/README.md` rules that only a human reviewer may set
        `reviewed`, after checking every number against the cited source page.
        So this asks for the name of whoever did that, and the adapter refuses
        without one: a status with nobody attached is the same unverified
        number wearing a better label.

        A core that belongs in the product still gets promoted by being added
        to `catalog/cores/*.yaml` and reviewed there -- this marks a local
        core as checked, it does not publish one.
        """
        from inductor_designer.adapters.catalog.overlay_repository import (
            CoreOverlayError,
            promote_overlay_core,
        )
        from inductor_designer.adapters.system.environment import (
            catalog_overlay_directory,
        )

        try:
            promote_overlay_core(catalog_overlay_directory(), part_number, reviewed_by)
        except (OSError, CoreOverlayError) as error:
            self._set_message(str(error))
            return False
        self.optionsChanged.emit()
        self.selectionChanged.emit()
        self._set_message(
            f"{part_number} marked reviewed by {reviewed_by.strip()}."
        )
        return True

    @Slot()
    def openMaterialStudio(self) -> None:
        self.materialStudioRequested.emit()

    @Slot()
    def refresh(self) -> None:
        """Re-read the pinned core/material after the session project itself
        was replaced wholesale (Open), rather than edited through this
        controller."""
        self._acknowledged = (
            self._session.project.design.manual_material_compatibility_acknowledged
        )
        self._set_message("")
        self.optionsChanged.emit()
        self.selectionChanged.emit()

    @Slot()
    def refreshLibrary(self) -> None:
        """Re-read the library after the Material Studio window closed."""
        try:
            outcome = revalidate_pinned_material(
                self._session.project, self._materials
            )
        except Exception as error:  # noqa: BLE001 - a QML slot must never raise
            # The overlay repository verifies sha256 and re-parses sources, so a
            # corrupt or half-written record raises a plain ValueError.
            self._set_message(f"Unable to reload the material library: {error}")
            return
        if outcome.cleared is None:
            self._session.set_status(outcome.message)
            self._set_message(outcome.message)
            self.optionsChanged.emit()
            self.selectionChanged.emit()
            return
        self._publish(outcome)
