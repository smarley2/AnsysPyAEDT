from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from inductor_designer.adapters.materials import FileOverlayMaterialRepository
from inductor_designer.adapters.persistence.project_repository import ProjectRepository
from inductor_designer.adapters.persistence.schema_repository import SchemaRepository
from inductor_designer.application.services.material_import import (
    approve_material,
    import_curve_csv,
    new_draft_record,
    review_material,
)
from inductor_designer.application.services.maxwell_export import (
    generate_run,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease
from inductor_designer.domain.project import CatalogCoreSelection, MaterialRevisionSelection
from inductor_designer.materials.records import (
    CurveConditions,
    MaterialRecord,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.replay import reproduce_record
from inductor_designer.materials.serde import sha256_hex
from inductor_designer.materials.validation import IssueSeverity, validate_record
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from inductor_designer.simulation.run_contracts import RunBackend, RunMode, RunRequest
from tests.fakes.femm_solver import RecordingFemmSolver
from tests.fakes.maxwell2d_exporter import RecordingMaxwell2dExporter
from tests.fakes.maxwell_exporter import RecordingMaxwell3dExporter
from tests.unit.application.test_geometry_model import CATALOG
from tests.unit.domain.test_project import make_project
from tools.reproduce_material import main as reproduce_main

ROOT = Path(__file__).resolve().parents[2]
CAPABILITIES = CapabilitySnapshot(
    release=AedtRelease(2025, 2),
    edition=AedtEdition.COMMERCIAL,
    include_dc_fields_3d=True,
    discovered_limits=(),
    evidence_source="recording integration test",
    review_status=CapabilityReviewStatus.REVIEWED,
)


def _source(filename: str, data: bytes) -> SourceProvenance:
    return SourceProvenance(
        kind=SourceKind.CSV,
        filename=filename,
        sha256=sha256_hex(data),
        url=f"https://example.com/{filename}",
        page=None,
        captured_at="2026-07-18T09:00:00+00:00",
        description="Synthetic reproducibility evidence",
    )


def _loss(frequency_hz: float, flux_density_t: float) -> float:
    return 2.5 * frequency_hz**1.4 * flux_density_t**2.3


def _record() -> tuple[MaterialRecord, dict[str, bytes]]:
    flux_densities = (0.05, 0.1, 0.2)
    sources = {
        "loss-10000.csv": (
            "x,y\n"
            + "".join(f"{b},{_loss(10_000.0, b)}\n" for b in flux_densities)
        ).encode(),
        "loss-50000.csv": (
            "x,y\n"
            + "".join(f"{b},{_loss(50_000.0, b)}\n" for b in flux_densities)
        ).encode(),
        "bh.csv": b"x,y\n0,0\n100,0.02\n200,0.04\n",
    }
    provenance = {
        filename: _source(filename, data)
        for filename, data in sources.items()
    }
    loss_series = tuple(
        import_curve_csv(
            sources[filename].decode(),
            series_id=f"loss-{frequency}",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="T",
            y_unit="W/m3",
            conditions=CurveConditions(float(frequency), 25.0, None),
            source=provenance[filename],
        )
        for frequency, filename in ((10_000, "loss-10000.csv"), (50_000, "loss-50000.csv"))
    )
    bh_series = import_curve_csv(
        sources["bh.csv"].decode(),
        series_id="bh",
        kind=SeriesKind.BH_CURVE,
        x_unit="A/m",
        y_unit="T",
        conditions=CurveConditions(None, 25.0, None),
        source=provenance["bh.csv"],
    )
    project = make_project()
    assert isinstance(project.design.core, CatalogCoreSelection)
    draft = new_draft_record(
        project.design.core.snapshot.material,
        series=(*loss_series, bh_series),
        sources=tuple(provenance.values()),
        created_at="2026-07-18T09:00:00+00:00",
        notes="Synthetic evidence only; no live solver claim.",
        mass_density_kg_per_m3=4800.0,
    )
    assert not any(issue.severity is IssueSeverity.ERROR for issue in validate_record(draft))
    approved = approve_material(
        review_material(draft, "reviewer@example.com"), "approver@example.com"
    )
    return approved, sources


def _arguments(root: Path, revision: str) -> list[str]:
    return [
        "--overlay-root",
        str(root),
        "--manufacturer",
        "Magnetics",
        "--name",
        "Kool Mu",
        "--grade",
        "60",
        "--revision",
        revision,
    ]


def test_material_sources_reproduce_through_project_and_recording_exports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    approved, sources = _record()
    overlay = tmp_path / "overlay"
    FileOverlayMaterialRepository(overlay).save(approved, sources)

    fresh_repository = FileOverlayMaterialRepository(overlay)
    loaded = fresh_repository.get(approved.ref, approved.revision_id)
    report = reproduce_record(
        loaded, fresh_repository.source_bytes(loaded.ref, loaded.revision_id)
    )
    assert report.matches
    assert reproduce_main(_arguments(overlay, loaded.revision_id)) == 0
    assert capsys.readouterr().out == "MATCH\n"

    project_repository = ProjectRepository(SchemaRepository(ROOT / "schemas"))
    project_path = tmp_path / "material-project.inductor.json"
    project = make_project()
    project_repository.save(
        replace(
            project,
            design=replace(
                project.design,
                core_material=MaterialRevisionSelection(
                    loaded.ref,
                    loaded.revision_id,
                    loaded,
                    "bh",
                ),
            ),
            operating_point=replace(
                project.operating_point,
                windings=tuple(
                    replace(winding, dc_current_a=0.0)
                    for winding in project.operating_point.windings
                ),
            ),
        ),
        project_path,
    )
    persisted_document = json.loads(project_path.read_text(encoding="utf-8"))
    assert persisted_document["schemaVersion"] == 5
    assert persisted_document["design"]["coreMaterial"]["bhSeriesId"] == "bh"
    fresh_project = project_repository.load(project_path)
    selection = fresh_project.design.core_material
    assert selection is not None
    assert selection.snapshot == loaded
    assert selection.bh_series_id == "bh"

    outcomes = tuple(
        generate_run(
            fresh_project,
            RunRequest(backend, RunMode.GENERATE_ONLY),
            CATALOG,
            CAPABILITIES,
            tmp_path / backend.value,
            maxwell3d_exporter=RecordingMaxwell3dExporter(),
            maxwell2d_exporter=RecordingMaxwell2dExporter(),
            femm_solver=RecordingFemmSolver(),
            run_id=f"reproducibility-{backend.value}",
            application_version="reproducibility-test",
        )
        for backend in (RunBackend.MAXWELL_3D, RunBackend.FEMM)
    )
    for outcome in outcomes:
        assert outcome.manifest.material.revision_id == loaded.revision_id
        assert outcome.manifest.material.bh_series_id == "bh"
        assert selection.snapshot.series

    record_tamper = tmp_path / "record-tamper"
    shutil.copytree(overlay, record_tamper)
    record_path = next(record_tamper.glob("*/*/*/*/record.json"))
    document = json.loads(record_path.read_text(encoding="utf-8"))
    document["series"][2]["points"][1]["y"] = 0.021
    record_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert reproduce_main(_arguments(record_tamper, loaded.revision_id)) == 1
    assert "CSV/JSON point disagreement for series bh" in capsys.readouterr().err

    source_tamper = tmp_path / "source-tamper"
    shutil.copytree(overlay, source_tamper)
    source_path = next(source_tamper.glob("*/*/*/*/sources/loss_10000_csv"))
    source_path.write_bytes(source_path.read_bytes() + b"tampered")
    assert reproduce_main(_arguments(source_tamper, loaded.revision_id)) == 1
    assert "sha256 mismatch for source loss-10000.csv" in capsys.readouterr().err
