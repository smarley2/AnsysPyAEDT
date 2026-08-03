"""The `Core & Material` screen (specification section 4.1).

The controller owns no rules: it converts the session project into QML rows and
routes every change through `core_material_selection`, so the filtering and the
never-substituting clear stay testable without Qt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.core_material_selection import (
    ClearedSelection,
    SelectionOutcome,
    apply_catalog_core,
    apply_manual_core,
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

    def _get_core_options(self) -> list[dict[str, object]]:
        pinned = self._session.project.design.core_material
        options = core_options(self._catalog, pinned.ref if pinned else None)
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

    @Slot()
    def openMaterialStudio(self) -> None:
        self.materialStudioRequested.emit()

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
