"""Exit-criterion proof for M7a (specification acceptance criterion 8).

Runs the preliminary estimator against the real shipped material overlay and
the real core catalog record, never against a fixture, and proves the
estimator's process boundary in a clean interpreter.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from inductor_designer.adapters.materials.overlay_repository import (
    FileOverlayMaterialRepository,
)
from inductor_designer.domain.project import (
    Design,
    InductorProject,
    MaterialRevisionSelection,
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
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.simulation.preliminary import (
    PreliminaryRequest,
    estimate_preliminary,
)
from inductor_designer.simulation.preliminary_contracts import (
    DiagnosticCode,
    ResultState,
)
from tools.build_catalog import build

ROOT = Path(__file__).resolve().parents[2]
REF = MaterialRef("Magnetics", "High Flux", "60")


def _real_project_request(tmp_path: Path) -> PreliminaryRequest:
    """The M5a validation material and core, with 5 A DC per winding."""
    from inductor_designer.adapters.catalog.sqlite_repository import (
        SqliteCatalogRepository,
    )

    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    core_record = catalog.get_core("C058071A2")
    conductor = catalog.get_conductor("AWG 18")
    assert core_record is not None
    assert conductor is not None

    repository = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = repository.list_revisions(REF)[0]
    snapshot = repository.get(REF, revision_id)
    selection = MaterialRevisionSelection(
        ref=REF,
        revision_id=revision_id,
        snapshot=snapshot,
        bh_series_id="bh-25c",
    )

    winding_ids = ("w1", "w2")
    project = InductorProject(
        project_id="m7a-exit-criterion",
        name="M7a exit-criterion project",
        description="",
        design=Design(
            core=None,
            windings=tuple(
                WindingDefinition(
                    winding_id=winding_id,
                    label=winding_id,
                    turns=10,
                    conductor_name="AWG 18",
                    mode=ConductorMode.SOLID,
                    start_angle_deg=0.0,
                    sector_deg=150.0,
                    min_spacing_m=0.0002,
                    min_clearance_m=0.001,
                    winding_direction=WindingDirection.CLOCKWISE,
                    terminal_intent="",
                )
                for winding_id in winding_ids
            ),
            core_material=selection,
            manual_material_compatibility_acknowledged=False,
        ),
        operating_point=OperatingPoint(
            frequency_hz=100_000.0,
            winding_temperature_c=20.0,
            core_temperature_c=25.0,
            windings=tuple(
                WindingOperatingPoint(
                    winding_id=winding_id,
                    ac_rms_current_a=2.0,
                    ac_phase_deg=0.0,
                    dc_current_a=5.0,
                    current_direction=CurrentDirection.FORWARD,
                )
                for winding_id in winding_ids
            ),
        ),
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
        conductors_by_winding={winding_id: conductor for winding_id in winding_ids},
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
            for winding_id in winding_ids
        },
    )


def test_preliminary_estimates_reproduce_without_qt_maxwell_or_femm(
    tmp_path: Path,
) -> None:
    """Specification acceptance criterion 8."""
    result = estimate_preliminary(_real_project_request(tmp_path))

    assert result.core.b_peak_magnitude.state is ResultState.ESTIMATED
    assert result.windings[0].j_ac_rms.state is ResultState.ESTIMATED
    assert result.windings[0].wire_loss.state is ResultState.ESTIMATED
    # 5 A DC with loss data recorded only at 0 A/m: core loss must be refused,
    # never invented by ignoring the DC-bias condition.
    assert (
        result.core.core_loss.code
        == DiagnosticCode.CORE_LOSS_NO_LOSS_DATA_FOR_DC_BIAS
    )
    assert result.totals.total_wire_loss.state is ResultState.ESTIMATED
    assert result.totals.total_loss.code == DiagnosticCode.TOTAL_LOSS_INCOMPLETE
    assert result.material_revision_id == _repository_revision()


def _repository_revision() -> str:
    """The pinned revision is whatever the overlay currently holds."""
    revisions = FileOverlayMaterialRepository(ROOT / "materials-overlay").list_revisions(REF)
    return revisions[0]


def test_the_estimator_imports_no_qt_and_no_solver() -> None:
    """Specification section 5 boundary, checked in a clean interpreter.

    Asserting on sys.modules inside the suite would only report what earlier
    tests imported, so this runs a fresh interpreter that imports the estimator
    and nothing else.
    """
    probe = (
        "import sys;"
        "import inductor_designer.simulation.preliminary;"
        "leaked=[name for name in sys.modules"
        " if name.split('.')[0] in {'PySide6', 'ansys', 'femm', 'sqlite3'}];"
        "print(leaked)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )

    assert completed.stdout.strip() == "[]", completed.stdout
