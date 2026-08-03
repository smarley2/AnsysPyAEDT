"""Specification section 11: the acceptance walk, without Qt, Maxwell, or FEMM.

The controllers are Qt objects, so this test needs an offscreen QGuiApplication,
but it starts no solver: it proves the flow's state transitions end to end
against the real catalog and the real material overlay.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.adapters.catalog.sqlite_repository import (  # noqa: E402
    SqliteCatalogRepository,
)
from inductor_designer.adapters.materials.overlay_repository import (  # noqa: E402
    FileOverlayMaterialRepository,
)
from inductor_designer.materials.identity import MaterialRef  # noqa: E402
from inductor_designer.materials.records import MaterialRecord, SeriesKind  # noqa: E402
from inductor_designer.simulation.preliminary_contracts import ResultState  # noqa: E402
from inductor_designer.ui.core_material_controller import (  # noqa: E402
    CoreMaterialController,
)
from inductor_designer.ui.guided_studio_controller import (  # noqa: E402
    GuidedStudioController,
)
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402
from tools.build_catalog import build  # noqa: E402

pytestmark = pytest.mark.ui

ROOT = Path(__file__).resolve().parents[2]
REF = MaterialRef("Magnetics", "High Flux", "60")


def bh_series_id(record: MaterialRecord) -> str:
    """Read the shipped series id; never predict one (it depends on the import)."""
    return next(
        series.series_id
        for series in record.series
        if series.kind is SeriesKind.BH_CURVE
    )


def test_the_acceptance_walk_produces_live_estimates(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    materials = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = materials.list_revisions(REF)[0]
    series_id = bh_series_id(materials.get(REF, revision_id))

    session = ProjectSession(make_project(), tmp_path / "walk.inductor.json", lambda p: None)
    core_material = CoreMaterialController(session, catalog, materials)
    windings = GuidedStudioController(session, catalog)
    preliminary = PreliminaryController(session, catalog)
    session.projectChanged.connect(preliminary.refresh)

    # 1. choose a material first, then a compatible core (either order).
    assert core_material.selectMaterial(
        REF.manufacturer, REF.name, REF.grade, revision_id, series_id
    )
    compatible = [row["partNumber"] for row in core_material.coreOptions]
    assert compatible, "the shipped catalog has no core for the shipped material"
    assert core_material.selectCatalogCore(str(compatible[0]))
    assert core_material.selectedMaterial["revisionId"] == revision_id

    # 3. one shared frequency plus both temperatures.
    assert windings.setOperatingPointField("frequencyHz", "100e3")
    assert windings.setOperatingPointField("windingTemperatureC", "20")
    assert windings.setOperatingPointField("coreTemperatureC", "25")

    # 4-5. numeric edits, then live preliminary results.
    assert windings.setWindingField("w1", "turns", "10")
    assert windings.setWindingField("w1", "dcCurrentA", "0")
    preliminary.refresh()

    assert preliminary.coreRows[0]["state"] == ResultState.ESTIMATED.value
    assert preliminary.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value
    assert preliminary.windingRows[0]["wireLoss"]["state"] == ResultState.ESTIMATED.value
    # 6. assumptions are always visible.
    assert preliminary.assumptions


def test_a_manual_core_estimates_flux_density_from_its_dimensions(tmp_path: Path) -> None:
    QGuiApplication.instance() or QGuiApplication([])
    index = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", index)
    catalog = SqliteCatalogRepository(index)
    materials = FileOverlayMaterialRepository(ROOT / "materials-overlay")
    revision_id = materials.list_revisions(REF)[0]
    series_id = bh_series_id(materials.get(REF, revision_id))

    session = ProjectSession(make_project())
    core_material = CoreMaterialController(session, catalog, materials)
    preliminary = PreliminaryController(session, catalog)

    assert core_material.applyManualCore(27.2, 13.8, 11.2, 0.0)
    assert core_material.setAcknowledged(True)
    assert core_material.selectMaterial(
        REF.manufacturer, REF.name, REF.grade, revision_id, series_id
    )
    preliminary.refresh()

    assert preliminary.coreRows[0]["state"] == ResultState.ESTIMATED.value
    assert any("Manual-core" in note for note in preliminary.assumptions)
