from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import Enum

from inductor_designer.domain.catalog_records import ReviewStatus
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    ManualCoreSelection,
)
from inductor_designer.domain.winding import WindingDefinition


class ValidationCategory(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    COMPATIBILITY = "compatibility"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    category: ValidationCategory
    code: str
    message: str
    path: str


_OVERRIDE_FIELDS = frozenset({"outer_diameter_m", "inner_diameter_m", "height_m"})


def _segments(start_deg: float, sector_deg: float) -> tuple[tuple[float, float], ...]:
    end = start_deg + sector_deg
    if end <= 360.0:
        return ((start_deg, end),)
    return ((start_deg, 360.0), (0.0, end - 360.0))


def _sectors_overlap(first: WindingDefinition, second: WindingDefinition) -> bool:
    return any(
        a_start < b_end and b_start < a_end
        for a_start, a_end in _segments(first.start_angle_deg, first.sector_deg)
        for b_start, b_end in _segments(second.start_angle_deg, second.sector_deg)
    )


def _sector_fields_valid(winding: WindingDefinition) -> bool:
    return 0.0 <= winding.start_angle_deg < 360.0 and 0.0 < winding.sector_deg <= 360.0


def _validate_core(project: InductorProject) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    design = project.design
    core = design.core
    if core is None:
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO,
                "core.missing",
                "No core is selected yet.",
                "design.core",
            )
        )
    elif isinstance(core, ManualCoreSelection):
        if (
            core.inner_diameter_m >= core.outer_diameter_m
            or core.outer_diameter_m <= 0
            or core.inner_diameter_m <= 0
            or core.height_m <= 0
            or core.corner_radius_m < 0
        ):
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "core.manual.dimensions",
                    "Manual core dimensions must be positive with inner < outer diameter.",
                    "design.core",
                )
            )
    elif isinstance(core, CatalogCoreSelection):
        if core.snapshot.review_status is ReviewStatus.DRAFT:
            issues.append(
                ValidationIssue(
                    ValidationCategory.WARNING,
                    "core.snapshot.draft",
                    f"Catalog record {core.part_number} is a draft pending review.",
                    "design.core.snapshot",
                )
            )
        for index, override in enumerate(core.overrides):
            if not override.reason.strip():
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "core.override.reason",
                        "Every manual override requires a non-empty reason.",
                        f"design.core.overrides[{index}]",
                    )
                )
            if override.field not in _OVERRIDE_FIELDS:
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "core.override.field",
                        f"Unknown override field: {override.field!r}.",
                        f"design.core.overrides[{index}]",
                    )
                )
    material = design.core_material
    if (
        isinstance(core, CatalogCoreSelection)
        and material is not None
        and core.snapshot.material != material.ref
    ):
        issues.append(
            ValidationIssue(
                ValidationCategory.ERROR,
                "core-material.incompatible",
                "The selected material does not match the catalog core material.",
                "design.coreMaterial",
            )
        )
    manual_pair = isinstance(core, ManualCoreSelection) and material is not None
    if manual_pair and not design.manual_material_compatibility_acknowledged:
        issues.append(
            ValidationIssue(
                ValidationCategory.ERROR,
                "core-material.manual-unacknowledged",
                "Manual core and material selections require compatibility acknowledgment.",
                "design.manualMaterialCompatibilityAcknowledged",
            )
        )
    elif (
        design.manual_material_compatibility_acknowledged
        and not manual_pair
    ):
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO,
                "core-material.acknowledgment-unused",
                "Manual material compatibility acknowledgment is not needed for this design.",
                "design.manualMaterialCompatibilityAcknowledged",
            )
        )
    return issues


def _validate_winding(winding: WindingDefinition, path: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    def error(code: str, message: str) -> None:
        issues.append(ValidationIssue(ValidationCategory.ERROR, code, message, path))

    if winding.turns < 1:
        error("winding.turns", "Turn count must be at least 1.")
    if not 0.0 <= winding.start_angle_deg < 360.0:
        error("winding.start_angle", "Start angle must satisfy 0 <= angle < 360 degrees.")
    if not 0.0 < winding.sector_deg <= 360.0:
        error("winding.sector", "Sector must satisfy 0 < sector <= 360 degrees.")
    if winding.min_spacing_m < 0 or winding.min_clearance_m < 0:
        error("winding.spacing", "Spacing and clearance must be non-negative.")
    return issues


def validate_project(
    project: InductorProject,
    *,
    known_conductors: Collection[str] | None = None,
) -> tuple[ValidationIssue, ...]:
    issues = _validate_core(project)

    windings = project.design.windings
    winding_ids = {winding.winding_id for winding in windings}
    seen_operating_ids: set[str] = set()
    for index, operating_point in enumerate(project.operating_point.windings):
        path = f"operatingPoint.windings[{index}]"
        if operating_point.winding_id not in winding_ids:
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "operating-point.winding.unknown",
                    f"Operating point references unknown winding {operating_point.winding_id!r}.",
                    path,
                )
            )
        if operating_point.winding_id in seen_operating_ids:
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "operating-point.winding.duplicate",
                    f"Duplicate operating point for winding {operating_point.winding_id!r}.",
                    path,
                )
            )
        seen_operating_ids.add(operating_point.winding_id)
    for winding_id in winding_ids - seen_operating_ids:
        issues.append(
            ValidationIssue(
                ValidationCategory.ERROR,
                "operating-point.winding.missing",
                f"Winding {winding_id!r} has no operating point.",
                "operatingPoint.windings",
            )
        )

    seen_ids: set[str] = set()
    for index, winding in enumerate(windings):
        path = f"design.windings[{index}]"
        issues.extend(_validate_winding(winding, path))
        if winding.winding_id in seen_ids:
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "winding.id.duplicate",
                    f"Duplicate winding_id: {winding.winding_id!r}.",
                    path,
                )
            )
        seen_ids.add(winding.winding_id)
        if known_conductors is not None and winding.conductor_name not in known_conductors:
            issues.append(
                ValidationIssue(
                    ValidationCategory.ERROR,
                    "winding.conductor.unknown",
                    f"Conductor {winding.conductor_name!r} is not in the catalog.",
                    path,
                )
            )

    if known_conductors is None and windings:
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO,
                "winding.conductor.unchecked",
                "Conductor references were not checked against a catalog.",
                "design.windings",
            )
        )

    checkable = [w for w in windings if _sector_fields_valid(w)]
    for i, first in enumerate(checkable):
        for second in checkable[i + 1 :]:
            if _sectors_overlap(first, second):
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "winding.sector.overlap",
                        f"Windings {first.winding_id!r} and {second.winding_id!r} "
                        "declare overlapping angular sectors.",
                        "design.windings",
                    )
                )
    return tuple(issues)
