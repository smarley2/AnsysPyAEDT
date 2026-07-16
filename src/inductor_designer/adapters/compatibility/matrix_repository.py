from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)


class MatrixCapabilityRepository:
    """CapabilitySnapshot source backed by compatibility/aedt-matrix.yml.

    A row is REVIEWED only when its status is "passed" and a reviewer is
    recorded; unknown release/edition pairs map to an UNREVIEWED snapshot so
    select_dc_bias_strategy blocks them naturally.
    """

    def __init__(self, matrix_path: Path) -> None:
        self._path = matrix_path

    def snapshot_for(self, release: AedtRelease, edition: AedtEdition) -> CapabilitySnapshot:
        data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        rows: list[dict[str, Any]] = data.get("rows", []) if isinstance(data, dict) else []
        for row in rows:
            if str(row.get("release")) == str(release) and row.get("edition") == edition.value:
                reviewed = row.get("status") == "passed" and bool(row.get("evidenceReviewedBy"))
                return CapabilitySnapshot(
                    release=release,
                    edition=edition,
                    include_dc_fields_3d=row.get("includeDcFields3d"),
                    discovered_limits=tuple(row.get("discoveredLimits") or ()),
                    evidence_source=f"aedt-matrix:{self._path.name}",
                    review_status=(
                        CapabilityReviewStatus.REVIEWED
                        if reviewed
                        else CapabilityReviewStatus.UNREVIEWED
                    ),
                )
        return CapabilitySnapshot(
            release=release,
            edition=edition,
            include_dc_fields_3d=None,
            discovered_limits=(),
            evidence_source=f"aedt-matrix:{self._path.name}:missing-row",
            review_status=CapabilityReviewStatus.UNREVIEWED,
        )
