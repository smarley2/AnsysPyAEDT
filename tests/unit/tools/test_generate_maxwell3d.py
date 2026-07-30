from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_maxwell_export import project_for_runs
from tools.generate_maxwell3d import main

ROOT = Path(__file__).resolve().parents[3]


def _fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "resolved.inductor.json"
    ProjectRepository(SchemaRepository(ROOT / "schemas")).save(
        project_for_runs(),
        fixture,
    )
    return fixture


def test_main_exports_sample_project_and_writes_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(_fixture(tmp_path)),
            "--work-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
        ],
        exporter=RecordingMaxwell3dExporter(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["projectSchemaVersion"] == 5
    assert payload["backend"] == "maxwell-3d"
    assert payload["mode"] == "generate-only"
    assert payload["status"] == "succeeded"
    assert payload["windings"][0]["acRmsCurrentA"] == 2.0
    assert payload["windings"][0]["acPeakCurrentA"] == pytest.approx(
        2.0 * math.sqrt(2.0)
    )


def test_main_writes_failed_run_manifest_when_exporter_raises(
    tmp_path: Path,
) -> None:
    class _RaisingMaxwell3dExporter(RecordingMaxwell3dExporter):
        def export(self, request: object) -> object:  # type: ignore[override]
            raise RuntimeError("CLI Maxwell 3D adapter failed")

    evidence = tmp_path / "run-manifest.json"

    exit_code = main(
        [
            "--project",
            str(_fixture(tmp_path)),
            "--work-directory",
            str(tmp_path / "out"),
            "--evidence",
            str(evidence),
        ],
        exporter=_RaisingMaxwell3dExporter(),
    )

    assert exit_code == 1
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["backend"] == "maxwell-3d"
    assert payload["status"] == "failed"
    assert payload["diagnostics"] == ["RuntimeError: CLI Maxwell 3D adapter failed"]
    assert payload["artifacts"] == []
    run_directory = next((tmp_path / "runs").iterdir())
    assert payload == json.loads(
        (run_directory / "run-manifest.json").read_text(encoding="utf-8")
    )


def test_the_run_lands_beside_the_project_document(tmp_path: Path) -> None:
    project_directory = tmp_path / "project"
    project_directory.mkdir()
    project_path = project_directory / "sample.inductor.json"
    ProjectRepository(SchemaRepository(ROOT / "schemas")).save(
        project_for_runs(),
        project_path,
    )
    work_directory = tmp_path / "work"
    evidence = work_directory / "generation-manifest.json"

    exit_code = main(
        [
            "--project",
            str(project_path),
            "--work-directory",
            str(work_directory),
            "--evidence",
            str(evidence),
        ],
        exporter=RecordingMaxwell3dExporter(),
    )

    assert exit_code == 0
    runs = sorted((project_directory / "runs").iterdir())
    assert len(runs) == 1
    assert runs[0].name.endswith("-maxwell-3d")
    manifest_path = runs[0] / "run-manifest.json"
    assert manifest_path.is_file()
    assert evidence.is_file()
    assert json.loads(evidence.read_text(encoding="utf-8")) == json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    assert not (work_directory / "runs").exists()
