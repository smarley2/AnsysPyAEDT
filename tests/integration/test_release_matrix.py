from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.application.services.maxwell_export import (
    MaxwellExportBlocked,
    export_maxwell2d,
    export_maxwell3d,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.application.test_maxwell_export import three_d_project

ROOT = Path(__file__).resolve().parents[2]
REAL_MATRIX = ROOT / "compatibility" / "aedt-matrix.yml"

SYNTHETIC = """\
schemaVersion: 1
rows:
  - release: "2025.2"
    edition: commercial
    status: passed
    includeDcFields3d: true
    discoveredLimits: []
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
  - release: "2024.2"
    edition: commercial
    status: passed
    includeDcFields3d: false
    discoveredLimits: []
    evidenceReviewedAt: "2026-07-17T00:00:00Z"
    evidenceReviewedBy: fabio
"""


def manifest_3d(matrix: Path, release: AedtRelease, tmp_path: Path) -> dict[str, object]:
    capabilities = MatrixCapabilityRepository(matrix).snapshot_for(
        release, AedtEdition.COMMERCIAL
    )
    project = replace(three_d_project(), target_release=release)  # type: ignore[type-var]
    outcome = export_maxwell3d(
        project, CATALOG, RecordingMaxwell3dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=capabilities,
    )
    return json.loads(generation_manifest_json(outcome))


def test_real_matrix_2025_2_identifies_native(tmp_path: Path) -> None:
    # includeDcFields3d reviewed true on 2026-07-17 (live probe on AEDT 2025.2).
    payload = manifest_3d(REAL_MATRIX, AedtRelease(2025, 2), tmp_path)
    assert payload["succeeded"] is True
    assert payload["dcBias"]["strategy"] == "native-include-dc-fields"
    assert payload["dcBias"]["approximate"] is False
    assert payload["solutionType"] == "AC Magnetic with DC"


def test_synthetic_native_row_identifies_native(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    payload = manifest_3d(matrix, AedtRelease(2025, 2), tmp_path)
    assert payload["dcBias"]["strategy"] == "native-include-dc-fields"
    assert payload["dcBias"]["approximate"] is False
    assert payload["dcBias"]["appliedCurrentsA"] is not None


def test_product_boundary_rejects_synthetic_2024_target(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")

    with pytest.raises(
        MaxwellExportBlocked,
        match="Only AEDT 2025 R2 Commercial",
    ):
        manifest_3d(matrix, AedtRelease(2024, 2), tmp_path)


def test_two_d_is_always_blocked_and_marked_approximate_model(tmp_path: Path) -> None:
    matrix = tmp_path / "m.yml"
    matrix.write_text(SYNTHETIC, encoding="utf-8")
    capabilities = MatrixCapabilityRepository(matrix).snapshot_for(
        AedtRelease(2025, 2), AedtEdition.COMMERCIAL
    )
    project = replace(three_d_project(), dimension_mode=ModelDimension.TWO_D)  # type: ignore[type-var]
    outcome = export_maxwell2d(
        project, CATALOG, RecordingMaxwell2dExporter(), tmp_path,  # type: ignore[arg-type]
        capabilities=capabilities,
    )
    payload = json.loads(generation_manifest_json(outcome))
    assert payload["succeeded"] is True
    assert payload["dimension"] == "2d"
    assert payload["dcBias"]["strategy"] == "blocked"
    assert any("approximate" in note for note in payload["notes"])
