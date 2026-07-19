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
    export_femm2d,
    export_maxwell3d,
    femm_manifest_json,
    generation_manifest_json,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease, ModelDimension
from inductor_designer.domain.project import CatalogCoreSelection, MaterialRevisionSelection
from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
    extract_points,
)
from inductor_designer.materials.records import (
    CurveConditions,
    MaterialRecord,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
)
from inductor_designer.materials.replay import reproduce_record
from inductor_designer.materials.serde import canonicalize_points, sha256_hex
from inductor_designer.materials.validation import IssueSeverity, validate_record
from inductor_designer.simulation.capabilities import (
    CapabilityReviewStatus,
    CapabilitySnapshot,
)
from tests.fakes.femm_solver import RecordingFemmSolver
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


def _source(kind: SourceKind, filename: str, data: bytes) -> SourceProvenance:
    return SourceProvenance(
        kind=kind,
        filename=filename,
        sha256=sha256_hex(data),
        url=f"https://example.com/{filename}",
        page=7 if kind is SourceKind.IMAGE else None,
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
        "loss-100000.png": b"\x89PNG\r\n\x1a\nsynthetic-loss-curve",
    }
    provenance = {
        filename: _source(
            SourceKind.IMAGE if filename.endswith(".png") else SourceKind.CSV,
            filename,
            data,
        )
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
    maximum_loss = _loss(100_000.0, flux_densities[-1])
    extraction = ExtractionRecord(
        crop=CropRegion(0, 0, 100, 100),
        x_axis=AxisCalibration(AxisScale.LINEAR, 0.0, 0.0, 100.0, 0.2),
        y_axis=AxisCalibration(AxisScale.LINEAR, 100.0, 0.0, 0.0, maximum_loss),
        pixel_points=tuple(
            PixelPoint(500.0 * b, 100.0 * (1.0 - _loss(100_000.0, b) / maximum_loss))
            for b in flux_densities
        ),
    )
    image_loss_series = PointSeries(
        series_id="loss-100000-image",
        kind=SeriesKind.LOSS_TABLE,
        x_unit="T",
        y_unit="W/m3",
        conditions=CurveConditions(100_000.0, 25.0, None),
        points=canonicalize_points(extract_points(extraction), "T", "W/m3"),
        source_filename="loss-100000.png",
        extraction=extraction,
    )
    project = make_project()
    assert isinstance(project.core, CatalogCoreSelection)
    draft = new_draft_record(
        project.core.snapshot.material,
        series=(*loss_series, bh_series, image_loss_series),
        sources=tuple(provenance.values()),
        created_at="2026-07-18T09:00:00+00:00",
        notes="Synthetic evidence only; no live solver claim.",
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
    project_repository.save(
        replace(
            make_project(),
            materials=(MaterialRevisionSelection(loaded.ref, loaded.revision_id, loaded, "bh"),),
        ),
        project_path,
    )
    persisted_document = json.loads(project_path.read_text(encoding="utf-8"))
    assert persisted_document["schemaVersion"] == 4
    assert persisted_document["materials"][0]["bhSeriesId"] == "bh"
    fresh_project = project_repository.load(project_path)
    assert fresh_project.materials[0].snapshot == loaded
    assert fresh_project.materials[0].bh_series_id == "bh"

    maxwell_outcome = export_maxwell3d(
        fresh_project,
        CATALOG,
        RecordingMaxwell3dExporter(),
        tmp_path / "maxwell",
        capabilities=CAPABILITIES,
    )
    femm_outcome = export_femm2d(
        replace(fresh_project, dimension_mode=ModelDimension.TWO_D),
        CATALOG,
        RecordingFemmSolver(),
        tmp_path / "femm",
        capabilities=CAPABILITIES,
        analyze=False,
    )
    for manifest in (
        json.loads(generation_manifest_json(maxwell_outcome)),
        json.loads(femm_manifest_json(femm_outcome)),
    ):
        assert manifest["coreMaterial"]["materialRevision"] == loaded.revision_id
        assert manifest["coreMaterial"]["bhSeriesId"] == "bh"
        assert manifest["coreMaterial"]["bhPointCount"] > 0

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
