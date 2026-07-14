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
    core = project.core
    if core is None:
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO, "core.missing", "No core is selected yet.", "core"
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
                    "core",
                )
            )
    elif isinstance(core, CatalogCoreSelection):
        if core.snapshot.review_status is ReviewStatus.DRAFT:
            issues.append(
                ValidationIssue(
                    ValidationCategory.WARNING,
                    "core.snapshot.draft",
                    f"Catalog record {core.part_number} is a draft pending review.",
                    "core.snapshot",
                )
            )
        for index, override in enumerate(core.overrides):
            if not override.reason.strip():
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "core.override.reason",
                        "Every manual override requires a non-empty reason.",
                        f"core.overrides[{index}]",
                    )
                )
            if override.field not in _OVERRIDE_FIELDS:
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "core.override.field",
                        f"Unknown override field: {override.field!r}.",
                        f"core.overrides[{index}]",
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
    if winding.ac_magnitude_a < 0 or winding.frequency_hz <= 0 or winding.dc_current_a < 0:
        error(
            "winding.excitation",
            "AC magnitude and DC current must be non-negative and frequency positive.",
        )
    return issues


def validate_project(
    project: InductorProject,
    *,
    known_conductors: Collection[str] | None = None,
) -> tuple[ValidationIssue, ...]:
    issues = _validate_core(project)

    seen_ids: set[str] = set()
    for index, winding in enumerate(project.windings):
        path = f"windings[{index}]"
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

    if known_conductors is None and project.windings:
        issues.append(
            ValidationIssue(
                ValidationCategory.INFO,
                "winding.conductor.unchecked",
                "Conductor references were not checked against a catalog.",
                "windings",
            )
        )

    checkable = [w for w in project.windings if _sector_fields_valid(w)]
    for i, first in enumerate(checkable):
        for second in checkable[i + 1 :]:
            if _sectors_overlap(first, second):
                issues.append(
                    ValidationIssue(
                        ValidationCategory.ERROR,
                        "winding.sector.overlap",
                        f"Windings {first.winding_id!r} and {second.winding_id!r} "
                        "declare overlapping angular sectors.",
                        "windings",
                    )
                )
    return tuple(issues)
