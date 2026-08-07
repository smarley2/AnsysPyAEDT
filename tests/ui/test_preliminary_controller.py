from __future__ import annotations

import os
from dataclasses import replace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import ManualCoreSelection  # noqa: E402
from inductor_designer.simulation.preliminary_contracts import (  # noqa: E402
    DiagnosticCode,
    ResultState,
)
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project,
    make_project_with_material,
)

pytestmark = pytest.mark.ui


def test_a_complete_project_reports_estimated_rows() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material())
    controller = PreliminaryController(session, CATALOG)

    assert len(controller.coreRows) == 6
    assert len(controller.windingRows) == 1
    assert len(controller.totalRows) == 3
    assert controller.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value
    assert controller.windingRows[0]["wireLength"]["state"] == ResultState.ESTIMATED.value
    assert controller.materialRevisionId == make_material_record().revision_id
    # The fixture record carries no B-H series, so flux density comes from its
    # relative permeability and no series id is pinned.
    assert controller.bhSeriesId == ""
    assert any("linear permeability" in note for note in controller.assumptions)
    assert controller.geometryIssues == []


def test_editing_the_project_refreshes_the_rows() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(make_project_with_material())
    controller = PreliminaryController(session, CATALOG)
    session.projectChanged.connect(controller.refresh)
    before = controller.windingRows[0]["jAcRms"]["text"]

    session.apply(
        replace(
            session.project,
            operating_point=replace(
                session.project.operating_point,
                windings=(
                    replace(
                        session.project.operating_point.windings[0],
                        ac_rms_current_a=4.0,
                    ),
                ),
            ),
        )
    )

    assert controller.windingRows[0]["jAcRms"]["text"] != before


def test_a_missing_material_leaves_current_density_estimated() -> None:
    """Specification section 4.3: one missing input affects only its dependents."""
    QGuiApplication.instance() or QGuiApplication([])
    # `make_project()` already ships with `core_material=None`.
    controller = PreliminaryController(ProjectSession(make_project()), CATALOG)

    assert controller.coreRows[0]["state"] == ResultState.UNAVAILABLE.value
    assert (
        controller.coreRows[0]["code"]
        == DiagnosticCode.FLUX_DENSITY_NO_MATERIAL_SELECTED
    )
    assert controller.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value


def test_broken_geometry_invalidates_only_geometry_dependent_rows() -> None:
    """Specification section 9."""
    QGuiApplication.instance() or QGuiApplication([])
    base = make_project_with_material()
    project = replace(
        base,
        design=replace(
            base.design,
            windings=(replace(base.design.windings[0], turns=100000),),
        ),
    )
    controller = PreliminaryController(ProjectSession(project), CATALOG)

    assert controller.geometryIssues != []
    assert (
        controller.windingRows[0]["wireLength"]["code"]
        == DiagnosticCode.WIRE_LOSS_NO_GEOMETRY
    )
    assert controller.windingRows[0]["jAcRms"]["state"] == ResultState.ESTIMATED.value
    assert controller.coreRows[0]["state"] == ResultState.ESTIMATED.value


def test_a_manual_core_project_cannot_be_built_with_a_non_finite_dimension() -> None:
    """The boundary refuses it, so refresh() never sees a non-finite path length."""
    QGuiApplication.instance() or QGuiApplication([])
    with pytest.raises(ValueError, match="must be finite"):
        ManualCoreSelection(float("nan"), 0.0138, 0.0112, 0.0)


def test_overflowing_manual_core_dimensions_are_reported_not_raised() -> None:
    """Finite dimensions whose product overflows must not crash refresh().

    With these dimensions `path_length_m = pi * (outer + inner) / 2` stays a
    (very large but) finite number, so flux density still estimates -- it is
    `volume_m3 = area * path_length_m` that overflows to `inf`. Reading
    `simulation/preliminary.py::_core_all` and `_core_estimates` confirms core
    loss is the only row this particular overflow reaches: it alone consumes
    `core.volume_m3`.

    `core_magnetic_properties` (which feeds these rows) computes the core's
    path length and volume with closed-form arithmetic, never packing, so it
    stays fast at any magnitude. `build_geometry_model` hands these same
    dimensions to `resolve_finished_core` and `pack_winding`, which used to
    enumerate every winding layer a 1e200 m bore admits and never return;
    `pack_winding` now bounds that enumeration by the requested turns, so the
    real winding can stay in the project (see
    `tests/unit/geometry/test_packing.py::test_extreme_core_dimensions_pack_without_spinning`).
    """
    QGuiApplication.instance() or QGuiApplication([])
    base = make_project_with_material()
    project = replace(
        base,
        design=replace(
            base.design,
            core=ManualCoreSelection(1e200, 0.5e200, 1e50, 0.0),
            # Acknowledged so the overflow this test targets is what blocks
            # core quantities, not the Manual-core compatibility gate.
            manual_material_compatibility_acknowledged=True,
        ),
    )

    controller = PreliminaryController(ProjectSession(project), CATALOG)

    assert controller.coreRows[0]["state"] == ResultState.ESTIMATED.value
    assert controller.coreRows[5]["state"] == ResultState.UNAVAILABLE.value
    assert (
        controller.coreRows[5]["code"] == DiagnosticCode.CORE_LOSS_NON_FINITE_VOLUME
    )


def test_denormal_manual_core_dimensions_are_reported_not_raised() -> None:
    """Finite dimensions can still overflow the model; the screen must survive."""
    QGuiApplication.instance() or QGuiApplication([])
    base = make_project_with_material()
    project = replace(
        base,
        design=replace(
            base.design,
            core=ManualCoreSelection(5e-320, 2.5e-320, 5e-320, 0.0),
            # Acknowledged so the denormal-input failure this test targets is
            # what blocks core quantities, not the Manual-core compatibility
            # gate.
            manual_material_compatibility_acknowledged=True,
        ),
    )

    controller = PreliminaryController(ProjectSession(project), CATALOG)

    assert controller.coreRows[0]["state"] == ResultState.UNAVAILABLE.value
    assert (
        controller.coreRows[0]["code"]
        == DiagnosticCode.FLUX_DENSITY_CORE_PATH_NOT_FINITE
    )


def test_a_catalog_failure_during_refresh_is_reported_not_raised() -> None:
    """`build_geometry_model` can now raise `GeometryModelError` for any
    repository failure; `refresh` already catches only that, so this proves the
    slot survives a locked/deleted catalog file instead of crashing Qt.
    """
    QGuiApplication.instance() or QGuiApplication([])

    class FailingCatalog:
        def get_core(self, part_number: str) -> None:
            return None

        def list_cores(self) -> tuple[object, ...]:
            return ()

        def get_conductor(self, name: str) -> None:
            return None

        def list_conductor_names(self) -> tuple[str, ...]:
            raise OSError("catalog file is locked")

    controller = PreliminaryController(
        ProjectSession(make_project_with_material()), FailingCatalog()  # type: ignore[arg-type]
    )

    assert any(
        "Catalog is unavailable" in issue for issue in controller.geometryIssues
    )


def test_assumptions_are_always_visible() -> None:
    QGuiApplication.instance() or QGuiApplication([])
    controller = PreliminaryController(
        ProjectSession(make_project_with_material()), CATALOG
    )

    assert any("connector" in note or "lead" in note for note in controller.assumptions)
