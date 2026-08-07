from __future__ import annotations

from dataclasses import fields, replace

import pytest

from inductor_designer.domain.project import (
    CatalogCoreSelection,
    CoreOverride,
    Design,
    InductorProject,
    ManualCoreSelection,
    MaterialRevisionSelection,
    MeshIntent,
    OperatingPoint,
    RequestedOutput,
    SimulationRecipe,
    WindingOperatingPoint,
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
        "terminal_intent": "",
    }
    values.update(overrides)
    return WindingDefinition(**values)  # type: ignore[arg-type]


def make_operating_point(
    *windings: WindingOperatingPoint,
    frequency_hz: float = 100_000.0,
) -> OperatingPoint:
    return OperatingPoint(
        frequency_hz=frequency_hz,
        winding_temperature_c=20.0,
        core_temperature_c=25.0,
        windings=windings
        or (
            WindingOperatingPoint(
                winding_id="w1",
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=5.0,
                current_direction=CurrentDirection.FORWARD,
            ),
        ),
    )


def make_project(**overrides: object) -> InductorProject:
    values: dict[str, object] = {
        "project_id": "3f0e8f5e-8f4e-4a5e-9d5b-6c4f2b1a0d9c",
        "name": "Boost inductor",
        "description": "",
        "design": Design(
            core=CatalogCoreSelection("0077071A7", make_core(), ()),
            windings=(make_winding(),),
            core_material=None,
            manual_material_compatibility_acknowledged=False,
        ),
        "operating_point": make_operating_point(),
        "simulation_recipe": SimulationRecipe(
            mesh_intent=MeshIntent.STANDARD,
            maximum_passes=10,
            percent_error=1.0,
            requested_outputs=(
                RequestedOutput.RESISTANCE,
                RequestedOutput.INDUCTANCE,
            ),
        ),
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
        mass_density_kg_per_m3=4800.0,
        steinmetz=None,
        notes="Approved scalar material.",
    )


def make_project_with_material(**overrides: object) -> InductorProject:
    """`make_project()` with its catalog core's own material revision pinned.

    `make_material_record()` is Magnetics Kool Mu 60, exactly
    `make_core().material`, so this pair is compatible. The record carries no
    series, so flux density comes from its relative permeability and
    `bh_series_id` stays None.
    """
    record = make_material_record()
    project = make_project(**overrides)
    return replace(
        project,
        design=replace(
            project.design,
            core_material=MaterialRevisionSelection(
                ref=record.ref,
                revision_id=record.revision_id,
                snapshot=record,
                bh_series_id=None,
            ),
        ),
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


def test_project_aggregate_holds_design_operating_point_and_recipe() -> None:
    project = make_project()
    assert {field.name for field in fields(InductorProject)} == {
        "project_id",
        "name",
        "description",
        "design",
        "operating_point",
        "simulation_recipe",
    }
    assert {field.name for field in fields(WindingDefinition)} == {
        "winding_id",
        "label",
        "turns",
        "conductor_name",
        "mode",
        "start_angle_deg",
        "sector_deg",
        "min_spacing_m",
        "min_clearance_m",
        "winding_direction",
        "terminal_intent",
    }
    assert isinstance(project.design.core, CatalogCoreSelection)
    assert project.design.windings[0].turns == 20
    assert project.operating_point.frequency_hz == 100_000.0
    assert project.operating_point.winding_temperature_c == 20.0
    assert project.operating_point.core_temperature_c == 25.0


def test_catalog_selection_rejects_part_number_mismatch() -> None:
    with pytest.raises(ValueError, match="part_number"):
        CatalogCoreSelection("9999", make_core(), ())


def test_manual_selection_and_empty_core_allowed() -> None:
    manual = ManualCoreSelection(0.0269, 0.0147, 0.0112, 0.0)
    manual_design = Design(manual, (make_winding(),), None, False)
    empty_design = Design(None, (make_winding(),), None, False)
    assert make_project(design=manual_design).design.core is manual
    assert make_project(design=empty_design).design.core is None


def test_winding_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="winding_id"):
        make_winding(winding_id="  ")


def test_project_rejects_blank_name() -> None:
    with pytest.raises(ValueError, match="name"):
        make_project(name=" ")


def test_project_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="project_id"):
        make_project(project_id=" ")


def test_winding_operating_point_rejects_blank_id() -> None:
    with pytest.raises(ValueError, match="winding_id"):
        WindingOperatingPoint(" ", 2.0, 0.0, 5.0, CurrentDirection.FORWARD)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_winding_operating_point_rejects_non_finite_numeric_values(value: float) -> None:
    for field in ("ac_rms_current_a", "ac_phase_deg", "dc_current_a"):
        values: dict[str, object] = {
            "winding_id": "w1",
            "ac_rms_current_a": 2.0,
            "ac_phase_deg": 0.0,
            "dc_current_a": 5.0,
            "current_direction": CurrentDirection.FORWARD,
        }
        values[field] = value
        with pytest.raises(ValueError, match=field):
            WindingOperatingPoint(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_operating_point_rejects_non_finite_numeric_values(value: float) -> None:
    for field in ("frequency_hz", "winding_temperature_c", "core_temperature_c"):
        values: dict[str, object] = {
            "frequency_hz": 100_000.0,
            "winding_temperature_c": 20.0,
            "core_temperature_c": 25.0,
        }
        values[field] = value
        with pytest.raises(ValueError, match=field):
            OperatingPoint(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("frequency_hz", [0.0, -1.0])
def test_operating_point_rejects_non_positive_frequency(frequency_hz: float) -> None:
    with pytest.raises(ValueError, match="frequency_hz"):
        make_operating_point(frequency_hz=frequency_hz)


@pytest.mark.parametrize("field", ["ac_rms_current_a", "dc_current_a"])
def test_winding_operating_point_rejects_negative_currents(field: str) -> None:
    values: dict[str, object] = {
        "winding_id": "w1",
        "ac_rms_current_a": 2.0,
        "ac_phase_deg": 0.0,
        "dc_current_a": 5.0,
        "current_direction": CurrentDirection.FORWARD,
    }
    values[field] = -0.1
    with pytest.raises(ValueError, match=field):
        WindingOperatingPoint(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("maximum_passes", [0, -1])
def test_simulation_recipe_rejects_non_positive_maximum_passes(maximum_passes: int) -> None:
    with pytest.raises(ValueError, match="maximum_passes"):
        SimulationRecipe(MeshIntent.STANDARD, maximum_passes, 1.0, ())


@pytest.mark.parametrize("maximum_passes", [float("inf"), float("-inf"), float("nan")])
def test_simulation_recipe_rejects_non_finite_maximum_passes(maximum_passes: float) -> None:
    with pytest.raises(ValueError, match="maximum_passes"):
        SimulationRecipe(MeshIntent.STANDARD, maximum_passes, 1.0, ())  # type: ignore[arg-type]


@pytest.mark.parametrize("percent_error", [0.0, -0.1])
def test_simulation_recipe_rejects_non_positive_percent_error(percent_error: float) -> None:
    with pytest.raises(ValueError, match="percent_error"):
        SimulationRecipe(MeshIntent.STANDARD, 10, percent_error, ())


@pytest.mark.parametrize("percent_error", [float("inf"), float("-inf"), float("nan")])
def test_simulation_recipe_rejects_non_finite_percent_error(percent_error: float) -> None:
    with pytest.raises(ValueError, match="percent_error"):
        SimulationRecipe(MeshIntent.STANDARD, 10, percent_error, ())


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


def test_manual_core_refuses_non_finite_dimensions() -> None:
    with pytest.raises(ValueError, match="outer_diameter_m must be finite"):
        ManualCoreSelection(float("nan"), 0.0138, 0.0112, 0.0)
    with pytest.raises(ValueError, match="height_m must be finite"):
        ManualCoreSelection(0.0272, 0.0138, float("inf"), 0.0)


def test_manual_core_still_accepts_dimensions_its_diagnostics_own() -> None:
    """Inverted or zero dimensions are reported downstream, not refused here."""
    inverted = ManualCoreSelection(0.010, 0.020, 0.005, 0.0)

    assert inverted.inner_diameter_m > inverted.outer_diameter_m


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
        mass_density_kg_per_m3=4800.0,
        steinmetz=snapshot.steinmetz,
        notes=snapshot.notes,
    )

    with pytest.raises(ValueError, match="revision_id"):
        MaterialRevisionSelection(transient.ref, transient.revision_id, transient)
