"""The Review screen (specification section 4.4).

Everything shown here is already computed elsewhere: the session project, the
preliminary controller's rows, the domain validator, and the last run's
evidence. Review composes them and binds the two ADR 0007 open actions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Signal, Slot

from inductor_designer.application.services.simulation_summary import (
    simulation_summary,
)
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    ManualCoreSelection,
)
from inductor_designer.domain.validation import validate_project

if TYPE_CHECKING:
    from pathlib import Path

    from inductor_designer.application.ports.catalog import CatalogRepository
    from inductor_designer.application.ports.path_opener import PathOpener
    from inductor_designer.ui.generation_controller import GenerationController
    from inductor_designer.ui.preliminary_controller import PreliminaryController
    from inductor_designer.ui.project_session import ProjectSession


class ReviewController(QObject):
    reviewChanged = Signal()

    def __init__(
        self,
        session: ProjectSession,
        preliminary: PreliminaryController,
        generation: GenerationController,
        catalog: CatalogRepository,
        opener: PathOpener,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._preliminary = preliminary
        self._generation = generation
        self._catalog = catalog
        self._opener = opener
        self._message = ""
        generation.linesChanged.connect(self.refresh)
        session.projectChanged.connect(self.refresh)
        # Ordering hazard: `main.py` connects `session.projectChanged` to
        # `preliminary_controller.refresh` AFTER this constructor runs, so on
        # every edit Qt fires the connection above (this refresh) before
        # `PreliminaryController` recomputes its rows -- Review would render
        # with Preliminary's pre-edit cache and nothing would tell it to try
        # again. Refreshing on Preliminary's own `resultChanged` closes that
        # gap. Do not remove this without re-checking the connection order in
        # `main.py`.
        preliminary.resultChanged.connect(self.refresh)

    def _core_rows(self) -> list[dict[str, str]]:
        design = self._session.project.design
        core = design.core
        rows: list[dict[str, str]] = []
        if isinstance(core, CatalogCoreSelection):
            rows.append({"label": "Core", "text": f"Catalog {core.part_number}"})
            rows.append(
                {
                    "label": "Core material identity",
                    "text": (
                        f"{core.snapshot.material.manufacturer} "
                        f"{core.snapshot.material.name} {core.snapshot.material.grade}"
                    ),
                }
            )
        elif isinstance(core, ManualCoreSelection):
            rows.append(
                {
                    "label": "Core",
                    "text": (
                        f"Manual toroid {core.outer_diameter_m * 1000.0:g} x "
                        f"{core.inner_diameter_m * 1000.0:g} x "
                        f"{core.height_m * 1000.0:g} mm"
                    ),
                }
            )
            rows.append(
                {
                    "label": "Manual compatibility acknowledged",
                    "text": (
                        "yes"
                        if design.manual_material_compatibility_acknowledged
                        else "no"
                    ),
                }
            )
        else:
            rows.append({"label": "Core", "text": "not selected"})
        material = design.core_material
        rows.append(
            {
                "label": "Pinned material revision",
                "text": (
                    "not selected"
                    if material is None
                    else (
                        f"{material.ref.manufacturer} {material.ref.name} "
                        f"{material.ref.grade} revision {material.revision_id}"
                        f" ({material.snapshot.status.value})"
                    )
                ),
            }
        )
        rows.append(
            {
                "label": "B-H series",
                "text": (
                    material.bh_series_id or "not selected"
                    if material is not None
                    else "not selected"
                ),
            }
        )
        return rows

    def _winding_rows(self) -> list[dict[str, str]]:
        project = self._session.project
        excitations = {
            item.winding_id: item for item in project.operating_point.windings
        }
        rows: list[dict[str, str]] = []
        for winding in project.design.windings:
            excitation = excitations.get(winding.winding_id)
            if excitation is None:
                rows.append(
                    {"label": winding.winding_id, "text": "no excitation recorded"}
                )
                continue
            rows.append(
                {
                    "label": f"{winding.winding_id} ({winding.label})",
                    "text": (
                        f"{winding.turns} turns of {winding.conductor_name}; "
                        f"AC {excitation.ac_rms_current_a:g} A RMS at "
                        f"{excitation.ac_phase_deg:g} deg; DC "
                        f"{excitation.dc_current_a:g} A; "
                        f"{excitation.current_direction.value}; "
                        f"wound {winding.winding_direction.value}"
                    ),
                }
            )
        return rows

    def _preliminary_rows(self) -> list[dict[str, str]]:
        # The PySide6 stubs type a `Property(list, ...)` attribute as `Property`
        # itself rather than as the wrapped list on instance access, so mypy
        # cannot see through `coreRows`, `totalRows`, `windingRows`,
        # `assumptions`, and `geometryIssues` below; every access is a runtime
        # list, exactly as declared on `PreliminaryController`.
        core_and_total_rows: list[dict[str, object]] = (
            self._preliminary.coreRows + self._preliminary.totalRows  # type: ignore[operator]
        )
        rows = [
            {"label": str(row["label"]), "text": str(row["text"])}
            for row in core_and_total_rows
        ]
        winding_rows: list[dict[str, object]] = self._preliminary.windingRows  # type: ignore[assignment]
        rows.extend(
            {
                "label": f"{row['windingId']} current density (AC RMS)",
                "text": str(row["jAcRms"]["text"]),  # type: ignore[index]
            }
            for row in winding_rows
        )
        assumptions: list[str] = self._preliminary.assumptions  # type: ignore[assignment]
        rows.extend({"label": "Limitation", "text": note} for note in assumptions)
        geometry_issues: list[str] = self._preliminary.geometryIssues  # type: ignore[assignment]
        rows.extend(
            {"label": "Geometry issue", "text": issue} for issue in geometry_issues
        )
        return rows

    def _run_rows(self) -> list[dict[str, str]]:
        document_path: str = self._session.documentPath  # type: ignore[assignment]
        rows = [
            {"label": "Project document", "text": document_path or "unsaved"},
        ]
        lines: list[str] = self._generation.lines  # type: ignore[assignment]
        rows.extend({"label": "Run log", "text": line} for line in lines)
        manifest = self._generation.failed_manifest
        if manifest is not None:
            rows.extend(
                {"label": "Solver notice", "text": warning}
                for warning in manifest.warnings
            )
        return rows

    def _get_sections(self) -> list[dict[str, object]]:
        return [
            {"title": "Core and material", "rows": self._core_rows()},
            {
                "title": "Shared operating point",
                "rows": [
                    {"label": "Summary", "text": line}
                    for line in simulation_summary(self._session.project)
                ],
            },
            {"title": "Winding excitations", "rows": self._winding_rows()},
            {"title": "Preliminary estimates", "rows": self._preliminary_rows()},
            {"title": "Run request", "rows": self._run_rows()},
        ]

    sections = Property(list, _get_sections, notify=reviewChanged)

    def _get_findings(self) -> list[dict[str, str]]:
        issues = validate_project(
            self._session.project,
            known_conductors=self._catalog.list_conductor_names(),
        )
        return [
            {
                "category": issue.category.value,
                "code": issue.code,
                "message": issue.message,
            }
            for issue in issues
        ]

    findings = Property(list, _get_findings, notify=reviewChanged)

    def _get_can_open_generated_file(self) -> bool:
        path = self._generation.last_generated_file
        return path is not None and path.exists()

    canOpenGeneratedFile = Property(
        bool, _get_can_open_generated_file, notify=reviewChanged
    )

    def _get_can_open_run_folder(self) -> bool:
        path = self._generation.last_run_directory
        return path is not None and path.is_dir()

    canOpenRunFolder = Property(bool, _get_can_open_run_folder, notify=reviewChanged)

    def _get_message(self) -> str:
        return self._message

    message = Property(str, _get_message, notify=reviewChanged)

    @Slot()
    def refresh(self) -> None:
        self.reviewChanged.emit()

    def _open(self, path: Path | None, what: str) -> bool:
        if path is None:
            # Both open actions are gated on the same run evidence, so before a
            # run they share one message: which button was pressed does not
            # change the reason ("no generated run yet"), only an actual
            # OSError from the opener is action-specific (see below).
            self._message = (
                "There is no generated run to open yet. Generate a run from "
                "the Simulation screen first."
            )
            self.reviewChanged.emit()
            return False
        try:
            self._opener.open_path(path)
        except (OSError, RuntimeError) as error:
            self._message = f"Unable to open the {what}: {error}"
            self.reviewChanged.emit()
            return False
        self._message = f"Opened the {what}."
        self.reviewChanged.emit()
        return True

    @Slot(result=bool)
    def openGeneratedFile(self) -> bool:
        return self._open(self._generation.last_generated_file, "generated solver file")

    @Slot(result=bool)
    def openRunFolder(self) -> bool:
        return self._open(self._generation.last_run_directory, "run folder")
