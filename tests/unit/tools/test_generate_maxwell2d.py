from __future__ import annotations

import json
from pathlib import Path

from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tools.generate_maxwell2d import main

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"


def test_main_exports_sample_project_forced_2d(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
            "--force-2d",
        ],
        exporter=RecordingMaxwell2dExporter(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["succeeded"] is True
    assert payload["dimension"] == "2d"
    assert payload["designName"] == "Inductor2D"
    assert payload["dcBias"]["strategy"] == "blocked"


def test_main_blocks_3d_project_without_force(tmp_path: Path) -> None:
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(tmp_path / "evidence.json"),
        ],
        exporter=RecordingMaxwell2dExporter(),
    )
    assert exit_code == 1


def test_main_exports_femm_backend(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
            "--force-2d",
            "--backend", "femm",
        ],
        femm_solver=RecordingFemmSolver(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["backend"] == "femm"
    assert set(payload["femmResults"]) == {"w1", "w2"}


def test_main_femm_backend_no_analyze(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
            "--force-2d",
            "--backend", "femm",
            "--no-analyze",
        ],
        femm_solver=RecordingFemmSolver(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["femmResults"] is None
