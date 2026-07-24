from __future__ import annotations

import json
from pathlib import Path

from inductor_designer.adapters.materials import FileOverlayMaterialRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.materials.records import MaterialRecord
from tests.unit.application.test_material_handoff import (
    HIGH_FLUX_REF,
    make_reproducible_material,
)
from tests.unit.domain.test_project import make_project
from tools.build_catalog import build
from tools.prepare_material_handoff import main

ROOT = Path(__file__).resolve().parents[3]


def _fixture_paths(tmp_path: Path) -> tuple[Path, Path, Path, MaterialRecord]:
    base_project = tmp_path / "base.inductor.json"
    ProjectRepository(SchemaRepository(ROOT / "schemas")).save(
        make_project(),
        base_project,
    )
    catalog = tmp_path / "catalog.sqlite"
    build(ROOT / "catalog", ROOT / "schemas" / "catalog", catalog)

    record, sources = make_reproducible_material(
        ref=HIGH_FLUX_REF,
        include_multi_frequency_loss=True,
    )
    overlay = tmp_path / "materials-overlay"
    FileOverlayMaterialRepository(overlay).save(record, sources)
    return base_project, catalog, overlay, record


def _args(
    base_project: Path,
    catalog: Path,
    overlay: Path,
    revision: str,
    output_project: Path,
    evidence: Path,
    *,
    core_part_number: str = "C058071A2",
) -> list[str]:
    return [
        "--base-project",
        str(base_project),
        "--catalog",
        str(catalog),
        "--schemas",
        str(ROOT / "schemas"),
        "--overlay-root",
        str(overlay),
        "--manufacturer",
        "Magnetics",
        "--name",
        "High Flux",
        "--grade",
        "60",
        "--revision",
        revision,
        "--core-part-number",
        core_part_number,
        "--bh-series-id",
        "bh-25c",
        "--output-project",
        str(output_project),
        "--evidence",
        str(evidence),
    ]


def test_prepare_material_handoff_writes_project_and_sanitized_evidence(
    tmp_path: Path,
) -> None:
    base_project, catalog, overlay, record = _fixture_paths(tmp_path)
    output_project = tmp_path / "generated" / "handoff.inductor.json"
    evidence_path = tmp_path / "generated" / "preflight.json"

    exit_code = main(
        _args(
            base_project,
            catalog,
            overlay,
            record.revision_id,
            output_project,
            evidence_path,
        )
    )

    assert exit_code == 0
    assert output_project.exists()
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    bh_series = next(series for series in record.series if series.series_id == "bh-25c")
    assert evidence["supportedEnvironment"] == {
        "aedtRelease": "2025.2",
        "edition": "commercial",
    }
    assert evidence["corePartNumber"] == "C058071A2"
    assert evidence["material"]["grade"] == "60"
    assert evidence["materialRevision"] == record.revision_id
    assert evidence["bhSeriesId"] == "bh-25c"
    assert evidence["bhPointCount"] == len(bh_series.points)
    assert len(evidence["lossFrequenciesHz"]) >= 2
    assert evidence["steinmetz"] is not None
    assert "points" not in json.dumps(evidence).casefold()
    assert str(tmp_path) not in json.dumps(evidence)


def test_prepare_material_handoff_removes_outputs_when_preflight_fails(
    tmp_path: Path,
) -> None:
    base_project, catalog, overlay, record = _fixture_paths(tmp_path)
    output_project = tmp_path / "generated" / "handoff.inductor.json"
    evidence_path = tmp_path / "generated" / "preflight.json"
    output_project.parent.mkdir()
    output_project.write_text("stale project", encoding="utf-8")
    evidence_path.write_text("stale evidence", encoding="utf-8")

    exit_code = main(
        _args(
            base_project,
            catalog,
            overlay,
            record.revision_id,
            output_project,
            evidence_path,
            core_part_number="C058071A2-missing",
        )
    )

    assert exit_code == 1
    assert not output_project.exists()
    assert not evidence_path.exists()
