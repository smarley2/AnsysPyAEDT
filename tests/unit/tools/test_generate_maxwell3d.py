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
            "--output-directory", str(tmp_path / "out"),
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
