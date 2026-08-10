from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

pytest.importorskip("PySide6")

from PySide6.QtCore import QObject  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

# Importing `QQuickWindow` before any QML engine is created is what makes
# PySide wrap `engine.rootObjects()[0]` as a `QQuickWindow` (with
# `grabWindow()`) instead of the plain `QWindow` base class it otherwise
# falls back to -- observed only when this module runs standalone, since
# some other already-imported test module normally does this first when the
# whole suite runs together.
from PySide6.QtQuick import QQuickWindow  # noqa: E402, F401

from inductor_designer.simulation.capabilities import (  # noqa: E402
    AedtEdition,
    AedtRelease,
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.main import create_engine  # noqa: E402
from inductor_designer.ui.preliminary_controller import (  # noqa: E402
    PreliminaryController,
)
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from inductor_designer.ui.simulation_controller import (  # noqa: E402
    SimulationController,
)
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import (  # noqa: E402
    make_material_record,
    make_project_with_material,
)

pytestmark = pytest.mark.ui

SUPPORTED = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


class RecordingOpener:
    def __init__(self) -> None:
        self.opened: list[Path] = []

    def open_path(self, path: Path) -> None:
        self.opened.append(path)


# QQmlApplicationEngine owns the window it loads: once the Python wrapper for
# the engine is garbage collected, the root window (and everything under it)
# is destroyed too, even though `root` is still referenced by the caller.
# Pin the engine and every controller passed to it for the test process
# lifetime instead of letting them drop the moment the helper returns (see
# tests/ui/test_winding_panel_qml.py for the same idiom).
_ENGINES: list[object] = []


def open_flow(
    step: int, *, dirty: bool = False
) -> tuple[QGuiApplication, QObject, ProjectSession]:
    app = QGuiApplication.instance() or QGuiApplication([])
    session = ProjectSession(
        make_project_with_material(), Path("boost.inductor.json"), lambda project: None
    )
    preliminary = PreliminaryController(session, CATALOG)
    generation = GenerationController(lambda _request: ("done",))
    simulation = SimulationController(session, generation, SUPPORTED)
    review = ReviewController(
        session, preliminary, generation, CATALOG, RecordingOpener()
    )
    if dirty:
        session.apply(replace(session.project, description="edited"))
    engine = create_engine(
        preliminary_controller=preliminary,
        simulation_controller=simulation,
        review_controller=review,
        generation_controller=generation,
        project_session=session,
    )
    _ENGINES.append((engine, preliminary, generation, simulation, review))
    root = engine.rootObjects()[0]
    root.findChild(QObject, "guidedStepList").setProperty("currentIndex", step)
    app.processEvents()
    return app, root, session


def _first_descendant(item: QObject, class_substring: str) -> QObject | None:
    for child in item.childItems():
        if class_substring in child.metaObject().className():
            return child
        found = _first_descendant(child, class_substring)
        if found is not None:
            return found
    return None


def _winding_table_row_cells(root: QObject) -> list[QObject]:
    """The first per-winding data row's cell items, in column order --
    matching `preliminaryWindingTableHeader`'s children one-to-one.
    """
    table = root.findChild(QObject, "preliminaryWindingTable")
    delegate = _first_descendant(table, "ColumnLayout")
    assert delegate is not None, "preliminaryWindingTable has no row delegate"
    row = _first_descendant(delegate, "RowLayout")
    assert row is not None, "the row delegate has no RowLayout of cells"
    return list(row.childItems())


def _winding_table_geometry(root: QObject, width: int) -> list[tuple[float, float]]:
    """(x, width) for each header column and each first-row data cell, at
    the given window width, after a forced layout settle.
    """
    root.setProperty("width", width)
    root.grabWindow()
    app = QGuiApplication.instance()
    for _ in range(5):
        app.processEvents()

    header = root.findChild(QObject, "preliminaryWindingTableHeader")
    assert header is not None
    header_cells = list(header.childItems())
    row_cells = _winding_table_row_cells(root)
    assert len(header_cells) == len(row_cells) == 8

    geometry: list[tuple[float, float]] = []
    for header_cell, row_cell in zip(header_cells, row_cells, strict=True):
        geometry.append((header_cell.property("x"), header_cell.property("width")))
        geometry.append((row_cell.property("x"), row_cell.property("width")))
    return geometry


def test_preliminary_winding_table_columns_are_fixed_and_aligned() -> None:
    """Regression test for Fabio's second report: "the columns of Windings
    does not have a fixed row, it is moving the width according to the width
    of the screen". A first attempt gave the header's seven columns
    `Layout.fillWidth: true` (so they could shrink on a narrow window) and
    then made the data cells match by giving them `Layout.fillWidth: true`
    too -- which does make header and data track each other, but means both
    now scale with the window, which is exactly what was reported as wrong.
    The fix is fixed-width columns (no `Layout.fillWidth` on any of the
    sixteen header/data cells) shared by both `RowLayout`s, so a column's
    width -- and a heading's position directly above its values -- never
    changes with the window.

    Asserts, for every column, at two very different window widths:
    - the header cell's `(x, width)` equals the data cell's `(x, width)`
      (header lines up with its data), and
    - the column's `width` is identical at both window widths (does not
      scale with the window).
    """
    _, root, _ = open_flow(2)

    geometry_by_width = {
        width: _winding_table_geometry(root, width) for width in (1000, 1786)
    }

    for width, geometry in geometry_by_width.items():
        for column in range(8):
            header_geom = geometry[2 * column]
            data_geom = geometry[2 * column + 1]
            assert header_geom == data_geom, (
                f"width={width}, column {column}: "
                f"header (x, width)={header_geom} data (x, width)={data_geom}"
            )

    narrow_widths = [geometry_by_width[1000][2 * c][1] for c in range(8)]
    wide_widths = [geometry_by_width[1786][2 * c][1] for c in range(8)]
    assert narrow_widths == wide_widths, (
        f"column widths must not scale with the window: "
        f"at 1000px={narrow_widths}, at 1786px={wide_widths}"
    )


def test_preliminary_page_shows_core_winding_totals_and_assumptions() -> None:
    _, root, _ = open_flow(2)

    for name in (
        "preliminaryPage",
        "preliminaryCoreTable",
        "preliminaryWindingTable",
        "preliminaryTotalsTable",
        "preliminaryAssumptions",
        "preliminaryMaterialLabel",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "preliminaryCoreTable").property("count") == 6
    assert root.findChild(QObject, "preliminaryTotalsTable").property("count") == 3
    assert (
        make_material_record().revision_id
        in root.findChild(QObject, "preliminaryMaterialLabel").property("text")
    )


def test_simulation_panel_exposes_every_run_choice() -> None:
    _, root, _ = open_flow(3)

    for name in (
        "simulationPanel",
        "simulationBackendCombo",
        "simulationModeLabel",
        "simulationMeshIntentCombo",
        "simulationMaximumPassesField",
        "simulationPercentErrorField",
        "simulationRequestedOutputs",
        "showSolverWindowCheckBox",
        "simulationGenerateButton",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "showSolverWindowCheckBox").property("enabled") is True


@pytest.mark.parametrize("width", (1000, 1786))
def test_simulation_run_grid_fields_track_the_column_not_their_native_width(
    width: int,
) -> None:
    """Regression guard for Fabio's report of "a similar issue on the right
    panel width" on the Simulation screen. `WindingPanel.qml` had a real,
    confirmed instance of this class of bug: a nested `GridLayout`'s
    `Layout.fillWidth` field lagging its enclosing column at a stale, larger
    width (root cause: `Layout.fillWidth`'s internal re-arrange, not an
    ordinary property binding, occasionally missing a step in this exact
    "`ColumnLayout` width bound to its own `ScrollView`" structure --
    `SimulationPanel.qml`'s "Maximum passes" / "Percent error" `GridLayout`
    has the identical structure). Extensive reproduction attempts (offscreen
    and native "windows" QPA, every window size from 1000-1786 x every
    height from 300-1119, toggled requested-output checkboxes, edited
    fields, switched backends, an unsupported-capability snapshot, and a
    dirty session) never actually caught this `GridLayout` stuck at a stale
    or oversized width -- but the class of bug it was hardened against
    (`width: parent.width` instead of `Layout.fillWidth: true`, matching
    `WindingPanel.qml`) is a real, previously-confirmed one for the
    identical structure, so this pins the contract precisely rather than
    relying on the weaker "does not overflow" containment check alone.

    Asserts the two numeric fields' rendered width always equals the
    `GridLayout`'s own width minus the wider of the two labels' width minus
    the column spacing -- i.e. the field is sized from the *current*
    available space, never left stuck at its own native/native-style
    `implicitWidth`.
    """
    _, root, _ = open_flow(3)
    root.setProperty("width", width)
    # `height: 300` forces a vertical scrollbar (see
    # `test_panel_layout_containment.py`'s `CRAMPED_HEIGHT`) -- the exact
    # condition report 2 used to reproduce `WindingPanel.qml`'s stale
    # `GridLayout` bug, since the scrollbar's reservation feeds back into
    # the `ColumnLayout`'s own width.
    root.setProperty("height", 300)
    root.grabWindow()
    app = QGuiApplication.instance()
    for _ in range(5):
        app.processEvents()

    passes_field = root.findChild(QObject, "simulationMaximumPassesField")
    percent_field = root.findChild(QObject, "simulationPercentErrorField")
    grid = passes_field.parent()
    assert "GridLayout" in grid.metaObject().className()

    labels = [
        child
        for child in grid.childItems()
        if child not in (passes_field, percent_field)
    ]
    assert len(labels) == 2
    label_column_width = max(label.property("width") for label in labels)
    column_spacing = grid.property("columnSpacing")
    expected_field_width = grid.property("width") - label_column_width - column_spacing

    for field in (passes_field, percent_field):
        assert field.property("width") == pytest.approx(expected_field_width, abs=1.0), (
            f"width={width}: field={field.objectName()} "
            f"rendered={field.property('width')} expected={expected_field_width} "
            f"(native implicitWidth={field.property('implicitWidth')})"
        )


def test_generate_is_disabled_and_explained_while_the_project_is_dirty() -> None:
    _, root, _ = open_flow(3, dirty=True)

    assert root.findChild(QObject, "simulationGenerateButton").property("enabled") is False
    reason = root.findChild(QObject, "simulationBlockedReason")
    assert reason is not None
    assert "save" in reason.property("text").casefold()


def test_review_page_lists_sections_and_disabled_open_actions() -> None:
    _, root, _ = open_flow(4)

    for name in (
        "reviewPage",
        "reviewSections",
        "reviewFindings",
        "openGeneratedFileButton",
        "openRunFolderButton",
        "reviewMessage",
    ):
        assert root.findChild(QObject, name) is not None, name
    assert root.findChild(QObject, "reviewSections").property("count") == 5
    assert root.findChild(QObject, "openGeneratedFileButton").property("enabled") is False
    assert root.findChild(QObject, "openRunFolderButton").property("enabled") is False
