from __future__ import annotations

from dataclasses import replace

from inductor_designer.domain.project import (
    CatalogCoreSelection,
    InductorProject,
    MaterialRevisionSelection,
)
from inductor_designer.materials.records import (
    MaterialRecord,
    MaterialStatus,
    SeriesKind,
)
from inductor_designer.materials.validation import IssueSeverity, validate_record


class MaterialSelectionError(ValueError):
    def __init__(self, issues: tuple[str, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def pin_material_revision(
    project: InductorProject,
    record: MaterialRecord,
    *,
    bh_series_id: str | None,
    manual_compatibility_acknowledged: bool = False,
) -> InductorProject:
    issues: list[str] = []
    core = project.design.core
    if isinstance(core, CatalogCoreSelection) and core.snapshot.material != record.ref:
        raise MaterialSelectionError(
            ("Selected material does not match the catalog core material.",)
        )
    if record.status not in (MaterialStatus.IMPORTED, MaterialStatus.APPROVED):
        issues.append("Material revision must be imported or approved before project selection.")
    issues.extend(
        issue.message
        for issue in validate_record(record)
        if issue.severity is IssueSeverity.ERROR
    )

    bh_series = tuple(series for series in record.series if series.kind is SeriesKind.BH_CURVE)
    if bh_series_id is None:
        if len(bh_series) > 1:
            issues.append(
                "Material revision contains multiple B-H series; select one explicitly."
            )
    elif not bh_series_id.strip():
        issues.append("B-H series ID cannot be blank.")
    else:
        selected = next(
            (series for series in record.series if series.series_id == bh_series_id),
            None,
        )
        if selected is None:
            issues.append(
                f"B-H series {bh_series_id!r} does not exist in the material revision."
            )
        elif selected.kind is not SeriesKind.BH_CURVE:
            issues.append(f"Series {bh_series_id!r} is not a B-H curve.")

    if issues:
        raise MaterialSelectionError(tuple(issues))

    selection = MaterialRevisionSelection(
        record.ref,
        record.revision_id,
        record,
        bh_series_id,
    )
    design = replace(
        project.design,
        core_material=selection,
        manual_material_compatibility_acknowledged=manual_compatibility_acknowledged,
    )
    return replace(project, design=design)
