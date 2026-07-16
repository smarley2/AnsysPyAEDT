from __future__ import annotations

from pathlib import Path

import pytest

from inductor_designer.adapters.pyaedt.maxwell2d import PyaedtMaxwell2dExporter
from inductor_designer.application.ports.maxwell2d_exporter import STAGE_NAMES_2D
from tests.contract.test_maxwell2d_exporter_contract import make_request
from tests.fakes.maxwell2d_app import FakeMaxwell2dApp, FakeMaxwell2dAppFactory

pytestmark = pytest.mark.usefixtures("fake_maxwell_boundary")


def run(tmp_path: Path, app: FakeMaxwell2dApp) -> object:
    exporter = PyaedtMaxwell2dExporter(app_factory=FakeMaxwell2dAppFactory(app))
    return exporter.export(make_request(tmp_path))


def test_full_stage_sequence_and_release(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    result = run(tmp_path, app)
    assert tuple(stage.name for stage in result.stages) == STAGE_NAMES_2D
    assert result.succeeded()
    assert app.released == [(True, True)]


def test_geometry_and_depth_calls(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp()
    run(tmp_path, app)
    names = [name for name, _ in app.calls]
    depth_sets = [k for n, k in app.calls if n == "set.model_depth"]
    assert depth_sets and depth_sets[0]["value"].endswith("meter")
    # core outer + bore + 8 conductors
    assert names.count("modeler.create_circle") == 2 + 8
    assert names.count("modeler.subtract") == 1
    coil_calls = [k for n, k in app.calls if n == "assign_coil"]
    assert len(coil_calls) == 8
    polarities = {k["polarity"] for k in coil_calls}
    assert polarities == {"Positive", "Negative"}
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1


def test_failing_stage_truncates_and_releases(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(raise_on="assign_matrix")
    result = run(tmp_path, app)
    assert not result.succeeded()
    assert result.stages[-1].name == "matrix"
    assert app.released == [(True, True)]
