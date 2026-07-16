from __future__ import annotations

import json
from pathlib import Path

from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tools.generate_maxwell3d import main

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "sample_geometry_project.inductor.json"


def test_main_exports_sample_project_and_writes_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    exit_code = main(
        [
            "--project", str(FIXTURE),
            "--output-directory", str(tmp_path / "out"),
            "--evidence", str(evidence),
        ],
        exporter=RecordingMaxwell3dExporter(),
    )
    assert exit_code == 0
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 2
    assert payload["succeeded"] is True
    assert payload["designName"] == "Inductor3D"
    assert [w["name"] for w in payload["windings"]] == ["w1", "w2"]
    assert payload["dcBias"]["strategy"] == "blocked"
