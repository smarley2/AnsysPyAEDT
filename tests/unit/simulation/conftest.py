from __future__ import annotations

import pytest

from inductor_designer.domain.catalog_records import (
    ConductorRecord,
    ConductorStandard,
    CoreFamily,
    CoreRecord,
    Dimension,
    ReviewStatus,
)
from inductor_designer.domain.project import (
    Design,
    InductorProject,
    MeshIntent,
    OperatingPoint,
    SimulationRecipe,
    WindingOperatingPoint,
)
from inductor_designer.domain.winding import (
    ConductorMode,
    CurrentDirection,
    WindingDefinition,
    WindingDirection,
)
from inductor_designer.geometry.packing import PackedWinding
from inductor_designer.simulation.preliminary import PreliminaryRequest
from tests.unit.simulation.test_magnetic_estimate import make_bh_series, make_material_selection


@pytest.fixture
def sample_request() -> PreliminaryRequest:
    """Two forward windings of 10 turns on a C058071A2-sized core at 100 kHz.

    The two windings are in phase, so their ampere-turns add: 10 turns * 2.0 A
    RMS each over a 0.0814 m path drives roughly 695 A/m peak AC field. The B-H
    series is recorded at 25 C, matching the default core temperature, and its
    points are chosen to cover that field, so flux density is Estimated. No
    loss series is present, so core loss is Unavailable -- the tests that need
    core loss add a series explicitly.
    """
    selection = make_material_selection(
        series=(
            make_bh_series(
                points=((0.0, 0.0), (200.0, 0.4), (700.0, 0.8), (1500.0, 1.0))
            ),
        ),
        bh_series_id="bh-25c",
    )
    core_record = CoreRecord(
        manufacturer="Magnetics",
        family=CoreFamily.POWDER_TOROID,
        part_number="C058071A2",
        material=selection.ref,
        coating="parylene",
        catalog_revision="rev1",
        source_url="https://example.invalid/C058071A2",
        source_page=1,
        outer_diameter=Dimension(nominal_m=0.0145, min_m=None, max_m=None),
        inner_diameter=Dimension(nominal_m=0.0079, min_m=None, max_m=None),
        height=Dimension(nominal_m=0.0064, min_m=None, max_m=None),
        effective_area_m2=6.56e-5,
        path_length_m=0.0814,
        volume_m3=5.34e-6,
        al_value_nh=61.0,
        review_status=ReviewStatus.REVIEWED,
        reviewed_by=None,
    )
    conductor = ConductorRecord(
        name="AWG 18",
        standard=ConductorStandard.AWG,
        bare_diameter_m=0.001024,
        grade1_diameter_m=None,
        grade2_diameter_m=None,
        source="test",
        catalog_revision="rev1",
        review_status=ReviewStatus.REVIEWED,
        reviewed_by=None,
    )
    windings = tuple(
        WindingDefinition(
            winding_id=winding_id,
            label=f"Winding {winding_id}",
            turns=10,
            conductor_name="AWG 18",
            mode=ConductorMode.SOLID,
            start_angle_deg=0.0,
            sector_deg=150.0,
            min_spacing_m=0.0005,
            min_clearance_m=0.0005,
            winding_direction=WindingDirection.CLOCKWISE,
            terminal_intent="lead",
        )
        for winding_id in ("w1", "w2")
    )
    operating_point = OperatingPoint(
        frequency_hz=100_000.0,
        winding_temperature_c=20.0,
        core_temperature_c=25.0,
        windings=tuple(
            WindingOperatingPoint(
                winding_id=winding_id,
                ac_rms_current_a=2.0,
                ac_phase_deg=0.0,
                dc_current_a=0.0,
                current_direction=CurrentDirection.FORWARD,
            )
            for winding_id in ("w1", "w2")
        ),
    )
    project = InductorProject(
        project_id="proj-1",
        name="Test Inductor",
        description="",
        design=Design(
            core=None,
            windings=windings,
            core_material=selection,
            manual_material_compatibility_acknowledged=False,
        ),
        operating_point=operating_point,
        simulation_recipe=SimulationRecipe(
            mesh_intent=MeshIntent.STANDARD,
            maximum_passes=10,
            percent_error=1.0,
            requested_outputs=(),
        ),
    )
    return PreliminaryRequest(
        project=project,
        core_record=core_record,
        conductors_by_winding={"w1": conductor, "w2": conductor},
        packings_by_winding={
            winding_id: PackedWinding(
                winding_id=winding_id,
                insulated_diameter_m=0.001094,
                sector_deg=150.0,
                start_deg=0.0,
                layers=(),
                lead_in_deg=0.0,
                lead_out_deg=0.0,
                wire_length_m=0.4,
            )
            for winding_id in ("w1", "w2")
        },
    )
