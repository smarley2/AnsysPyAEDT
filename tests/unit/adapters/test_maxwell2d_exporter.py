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
    assert names.index("set.model_depth") < names.index("create_setup")
    # core outer + bore + 8 conductors
    assert names.count("modeler.create_circle") == 2 + 8
    assert names.count("modeler.subtract") == 1
    coil_calls = [k for n, k in app.calls if n == "assign_coil"]
    assert len(coil_calls) == 8
    polarities = {k["polarity"] for k in coil_calls}
    assert polarities == {"Positive", "Negative"}
    winding_calls = [k for n, k in app.calls if n == "assign_winding"]
    assert len(winding_calls) == 1
    region_calls = [k for n, k in app.calls if n == "modeler.create_region"]
    assert region_calls == [{"pad_value": 100.0, "pad_type": "Percentage Offset"}]
    balloon_calls = [k for n, k in app.calls if n == "assign_balloon"]
    assert len(balloon_calls) == 1
    assert balloon_calls[0]["assignment"] == [
        "Region_edge1",
        "Region_edge2",
        "Region_edge3",
        "Region_edge4",
    ]
    assert balloon_calls[0]["boundary"] == "Balloon"


def test_failing_stage_truncates_and_releases(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(raise_on="assign_matrix")
    result = run(tmp_path, app)
    assert not result.succeeded()
    assert result.stages[-2].name == "matrix"
    assert result.stages[-2].succeeded is False
    assert "boom" in result.stages[-2].message
    assert result.stages[-1].name == "save"
    assert result.stages[-1].succeeded is True
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_falsy_region_return_fails_stage_and_still_saves(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(falsy_on="create_region")
    result = run(tmp_path, app)
    assert not result.succeeded()
    assert result.stages[-2].name == "region"
    assert result.stages[-2].succeeded is False
    assert result.stages[-1].name == "save"
    assert result.stages[-1].succeeded is True
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]


def test_falsy_balloon_return_fails_stage_and_still_saves(tmp_path: Path) -> None:
    app = FakeMaxwell2dApp(falsy_on="assign_balloon")
    result = run(tmp_path, app)
    assert not result.succeeded()
    assert result.stages[-2].name == "region"
    assert result.stages[-2].succeeded is False
    assert "assign_balloon" in result.stages[-2].message
    assert result.stages[-1].name == "save"
    assert result.stages[-1].succeeded is True
    saves = [k for n, k in app.calls if n == "save_project"]
    assert len(saves) == 1
    assert app.released == [(True, True)]
