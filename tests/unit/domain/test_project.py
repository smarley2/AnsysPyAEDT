from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from tests.unit.domain.test_catalog_records import make_core


def make_winding(**overrides: object) -> WindingDefinition:
    values: dict[str, object] = {
        "winding_id": "w1",
        "label": "Primary",
        "turns": 20,
        "conductor_name": "AWG 18",
        "mode": ConductorMode.SOLID,
        "start_angle_deg": 0.0,
        "sector_deg": 150.0,
        "min_spacing_m": 0.0002,
        "min_clearance_m": 0.001,
        "winding_direction": WindingDirection.CLOCKWISE,
        "current_direction": CurrentDirection.FORWARD,
        "terminal_intent": "",
        "ac_magnitude_a": 2.0,
        "ac_phase_deg": 0.0,
        "frequency_hz": 100_000.0,
        "dc_current_a": 5.0,
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def make_project(**overrides: object) -> InductorProject:
    values: dict[str, object] = {
        "project_id": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "name": "Boost inductor",
        "description": "",
        "target_release": AedtRelease(2025, 2),
        "target_edition": AedtEdition.COMMERCIAL,
        "dimension_mode": ModelDimension.THREE_D,
        "core": CatalogCoreSelection("0077071A7", make_core(), ()),
        "windings": (make_winding(),),
    }
    values.update(overrides)
    return InductorProject(**values)  # type: ignore[arg-type]


def make_material_record() -> MaterialRecord:
    return MaterialRecord(
        ref=MaterialRef("Magnetics", "Kool Mu", "60"),
        revision_id="0123456789ab",
        status=MaterialStatus.APPROVED,
        created_at="2026-07-17T08:32:00+00:00",
        reviewed_by="reviewer@example.com",
        approved_by="approver@example.com",
        sources=(),
        series=(),
        relative_permeability=60.0,
        steinmetz=None,
        notes="Approved scalar material.",
    )


def make_material_series(
    series_id: str = "bh-25c",
    kind: SeriesKind = SeriesKind.BH_CURVE,
) -> PointSeries:
    if kind is SeriesKind.BH_CURVE:
        x_unit, y_unit = "A/m", "T"
        conditions = CurveConditions(None, 25.0, None)
        points = (CurvePoint(0.0, 0.0), CurvePoint(100.0, 0.025))
    else:
        x_unit, y_unit = "T", "W/m3"
        conditions = CurveConditions(100_000.0, 25.0, None)
        points = (CurvePoint(0.05, 1200.0), CurvePoint(0.1, 4500.0))
    return PointSeries(
        series_id=series_id,
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        conditions=conditions,
        points=points,
        source_filename="curve.csv",
        extraction=None,
    )


def material_record_with_series(*series: PointSeries) -> MaterialRecord:
    source = SourceProvenance(
        kind=SourceKind.CSV,
        filename="curve.csv",
        sha256="0" * 64,
        url="https://example.com/material.pdf",
        page=1,
        captured_at="2026-07-17T08:32:00+00:00",
        description="Material curves",
    )
    return replace(make_material_record(), sources=(source,), series=series)


def test_project_aggregate_holds_selection_and_windings() -> None:
    project = make_project()
    assert isinstance(project.core, CatalogCoreSelection)
    assert project.windings[0].turns == 20


def test_catalog_selection_rejects_part_number_mismatch() -> None:
    with pytest.raises(ValueError, match="part_number"):
        CatalogCoreSelection("9999", make_core(), ())


def test_manual_selection_and_empty_core_allowed() -> None:
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0)
    assert make_project(core=manual).core is manual
    assert make_project(core=None).core is None


def test_winding_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="winding_id"):
        make_winding(winding_id="  ")


def test_project_rejects_blank_name() -> None:
    with pytest.raises(ValueError, match="name"):
        make_project(name=" ")


def test_override_carries_reason() -> None:
    override = CoreOverride(field="outer_diameter_m", value=0.027, reason="measured sample")
    assert override.reason == "measured sample"


def test_material_revision_selection_matches_snapshot_identity() -> None:
    snapshot = make_material_record()

    selection = MaterialRevisionSelection(snapshot.ref, snapshot.revision_id, snapshot)

    assert selection.snapshot is snapshot


def test_material_revision_selection_preserves_explicit_bh_series() -> None:
    snapshot = material_record_with_series(
        make_material_series(),
        make_material_series("loss-100khz", SeriesKind.LOSS_TABLE),
    )

    selection = MaterialRevisionSelection(
        snapshot.ref,
        snapshot.revision_id,
        snapshot,
        bh_series_id="bh-25c",
    )

    assert selection.bh_series_id == "bh-25c"


@pytest.mark.parametrize("bh_series_id", ["", "  "])
def test_material_revision_selection_rejects_blank_bh_series_id(
    bh_series_id: str,
) -> None:
    snapshot = material_record_with_series(make_material_series())

    with pytest.raises(ValueError, match="bh_series_id cannot be blank"):
        MaterialRevisionSelection(
            snapshot.ref,
            snapshot.revision_id,
            snapshot,
            bh_series_id=bh_series_id,
        )


def test_material_revision_selection_rejects_unknown_bh_series_id() -> None:
    snapshot = material_record_with_series(make_material_series())

    with pytest.raises(ValueError, match="must name a series in snapshot"):
        MaterialRevisionSelection(
            snapshot.ref,
            snapshot.revision_id,
            snapshot,
            bh_series_id="missing",
        )


def test_material_revision_selection_rejects_non_bh_series_id() -> None:
    snapshot = material_record_with_series(
        make_material_series("loss-100khz", SeriesKind.LOSS_TABLE)
    )

    with pytest.raises(ValueError, match="must name a B-H curve"):
        MaterialRevisionSelection(
            snapshot.ref,
            snapshot.revision_id,
            snapshot,
            bh_series_id="loss-100khz",
        )


@pytest.mark.parametrize(
    "series",
    [
        (),
        (make_material_series(),),
        (make_material_series(), make_material_series("bh-100c")),
    ],
)
def test_material_revision_selection_allows_null_bh_series_id(
    series: tuple[PointSeries, ...],
) -> None:
    snapshot = material_record_with_series(*series) if series else make_material_record()

    selection = MaterialRevisionSelection(
        snapshot.ref,
        snapshot.revision_id,
        snapshot,
        bh_series_id=None,
    )

    assert selection.bh_series_id is None


def test_material_revision_selection_rejects_mismatched_ref() -> None:
    snapshot = make_material_record()

    with pytest.raises(ValueError, match="ref"):
        MaterialRevisionSelection(
            MaterialRef("Magnetics", "Kool Mu", "75"), snapshot.revision_id, snapshot
        )


def test_material_revision_selection_rejects_mismatched_revision() -> None:
    snapshot = make_material_record()

    with pytest.raises(ValueError, match="revision_id"):
        MaterialRevisionSelection(snapshot.ref, "abcdef012345", snapshot)


def test_material_revision_selection_rejects_blank_revision() -> None:
    snapshot = make_material_record()
    transient = MaterialRecord(
        ref=snapshot.ref,
        revision_id="",
        status=MaterialStatus.DRAFT,
        created_at=snapshot.created_at,
        reviewed_by=None,
        approved_by=None,
        sources=snapshot.sources,
        series=snapshot.series,
        relative_permeability=snapshot.relative_permeability,
        steinmetz=snapshot.steinmetz,
        notes=snapshot.notes,
    )

    with pytest.raises(ValueError, match="revision_id"):
        MaterialRevisionSelection(transient.ref, transient.revision_id, transient)
