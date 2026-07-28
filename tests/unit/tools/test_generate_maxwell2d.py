from __future__ import annotations

import json
from pathlib import Path

import pytest

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.unit.application.test_maxwell_export import project_for_runs
from tools.generate_maxwell2d import main

ROOT = Path(__file__).resolve().parents[3]


def _fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "resolved.inductor.json"
    ProjectRepository(SchemaRepository(ROOT / "schemas")).save(
        project_for_runs(),
        fixture,
    )
    return fixture


def test_main_exports_sample_project_to_maxwell_2d(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(_fixture(tmp_path)),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
        ],
        exporter=RecordingMaxwell2dExporter(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["backend"] == "maxwell-2d"
    assert payload["mode"] == "generate-only"
    assert payload["status"] == "succeeded"
    assert payload["dimensionalRepresentation"] == "equivalent-cross-section"


def test_main_writes_failed_run_manifest_when_exporter_raises(
    tmp_path: Path,
) -> None:
    class _RaisingMaxwell2dExporter(RecordingMaxwell2dExporter):
        def export(self, request: object) -> object:  # type: ignore[override]
            raise RuntimeError("CLI Maxwell 2D adapter failed")

    evidence = tmp_path / "run-manifest.json"

    exit_code = main(
        [
            "--project",
            str(_fixture(tmp_path)),
            "--output-directory",
            str(tmp_path / "out"),
            "--evidence",
            str(evidence),
        ],
        exporter=_RaisingMaxwell2dExporter(),
    )

    assert exit_code == 1
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["backend"] == "maxwell-2d"
    assert payload["status"] == "failed"
    assert payload["diagnostics"] == ["RuntimeError: CLI Maxwell 2D adapter failed"]
    assert payload["artifacts"] == []


def test_force_2d_option_is_removed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--project",
                str(_fixture(tmp_path)),
                "--output-directory",
                str(tmp_path / "out"),
                "--evidence",
                str(tmp_path / "evidence.json"),
                "--force-2d",
            ],
            exporter=RecordingMaxwell2dExporter(),
        )


def test_main_exports_femm_backend(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(_fixture(tmp_path)),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
            "--backend", "femm",
        ],
        femm_solver=RecordingFemmSolver(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["backend"] == "femm"
    assert payload["mode"] == "generate-only"
    assert payload["status"] == "succeeded"
    assert payload["results"] is None


def test_no_analyze_option_is_removed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--project",
                str(_fixture(tmp_path)),
                "--output-directory",
                str(tmp_path / "out"),
                "--evidence",
                str(tmp_path / "evidence.json"),
                "--backend",
                "femm",
                "--no-analyze",
            ],
            femm_solver=RecordingFemmSolver(),
        )
