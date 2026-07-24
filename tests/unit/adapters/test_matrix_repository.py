from __future__ import annotations

from pathlib import Path

import yaml

from inductor_designer.adapters.compatibility.matrix_repository import (
    MatrixCapabilityRepository,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import CapabilityReviewStatus

ROOT = Path(__file__).resolve().parents[3]
REAL_MATRIX = ROOT / "compatibility" / "aedt-matrix.yml"


def test_real_matrix_contains_only_the_supported_environment() -> None:
    data = yaml.safe_load(REAL_MATRIX.read_text(encoding="utf-8"))
    assert [
        (row["release"], row["edition"])
        for row in data["rows"]
    ] == [("2025.2", "commercial")]

SYNTHETIC = """\
schemaVersion: 1
rows:
  - release: "2025.2"
    edition: commercial
    status: passed
    includeDcFields3d: true
    discoveredLimits: ["no-hpc"]
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


def test_real_matrix_reviewed_row_maps_to_snapshot() -> None:
    repo = MatrixCapabilityRepository(REAL_MATRIX)
    snapshot = repo.snapshot_for(AedtRelease(2025, 2), AedtEdition.COMMERCIAL)
    assert snapshot.review_status is CapabilityReviewStatus.REVIEWED
    # Reviewed true on 2026-07-17 via live probe (AC Magnetic with DC).
    assert snapshot.include_dc_fields_3d is True
    assert snapshot.evidence_source == "aedt-matrix:aedt-matrix.yml"


def test_out_of_scope_row_is_unreviewed() -> None:
    repo = MatrixCapabilityRepository(REAL_MATRIX)
    snapshot = repo.snapshot_for(AedtRelease(2024, 2), AedtEdition.COMMERCIAL)
    assert snapshot.review_status is CapabilityReviewStatus.UNREVIEWED


def test_missing_row_is_unreviewed_with_marker(tmp_path: Path) -> None:
    path = tmp_path / "m.yml"
    path.write_text(SYNTHETIC, encoding="utf-8")
    snapshot = MatrixCapabilityRepository(path).snapshot_for(
        AedtRelease(2026, 1), AedtEdition.STUDENT
    )
    assert snapshot.review_status is CapabilityReviewStatus.UNREVIEWED
    assert snapshot.evidence_source.endswith("missing-row")


def test_synthetic_rows_carry_flags(tmp_path: Path) -> None:
    path = tmp_path / "m.yml"
    path.write_text(SYNTHETIC, encoding="utf-8")
    repo = MatrixCapabilityRepository(path)
    native = repo.snapshot_for(AedtRelease(2025, 2), AedtEdition.COMMERCIAL)
    assert native.include_dc_fields_3d is True
    assert native.discovered_limits == ("no-hpc",)
    assert native.review_status is CapabilityReviewStatus.REVIEWED
    fallback = repo.snapshot_for(AedtRelease(2024, 2), AedtEdition.COMMERCIAL)
    assert fallback.include_dc_fields_3d is False
    assert fallback.review_status is CapabilityReviewStatus.REVIEWED
