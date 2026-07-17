from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.materials.calibration import (
    AxisCalibration,
    AxisScale,
    CropRegion,
    ExtractionRecord,
    PixelPoint,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    MaterialRecord,
    MaterialStatus,
    PointSeries,
    SeriesKind,
    SourceKind,
    SourceProvenance,
    SteinmetzFit,
    approve_record,
    review_record,
)
from inductor_designer.materials.serde import (
    material_record_from_json,
    material_record_json,
    material_record_to_json,
    parse_points_csv,
    points_csv,
    revision_id_for,
    sha256_hex,
)


def _record() -> MaterialRecord:
    extraction = ExtractionRecord(
        crop=CropRegion(left=10, top=20, width=300, height=200),
        x_axis=AxisCalibration(AxisScale.LINEAR, 10.0, 0.0, 310.0, 300.0),
        y_axis=AxisCalibration(AxisScale.LOG, 220.0, 1.0, 20.0, 1000.0),
        pixel_points=(PixelPoint(10.0, 220.0), PixelPoint(160.0, 120.0)),
    )
    sources = (
        SourceProvenance(
            kind=SourceKind.IMAGE,
            filename="bh.png",
            sha256="a" * 64,
            url="https://example.com/datasheet.pdf",
            page=4,
            captured_at="2026-07-17T08:30:00+00:00",
            description="B-H curve",
        ),
        SourceProvenance(
            kind=SourceKind.CSV,
            filename="loss.csv",
            sha256="b" * 64,
            url="https://example.com/loss.csv",
            page=None,
            captured_at="2026-07-17T08:31:00+00:00",
            description="Core-loss table",
        ),
    )
    series = (
        PointSeries(
            series_id="bh_25c",
            kind=SeriesKind.BH_CURVE,
            x_unit="Oe",
            y_unit="G",
            conditions=CurveConditions(None, 25.0, 0.0),
            points=(CurvePoint(0.0, 0.0), CurvePoint(79.577471546, 0.1)),
            source_filename="bh.png",
            extraction=extraction,
        ),
        PointSeries(
            series_id="loss_100khz",
            kind=SeriesKind.LOSS_TABLE,
            x_unit="mT",
            y_unit="mW/cm3",
            conditions=CurveConditions(100_000.0, 25.0, None),
            points=(CurvePoint(0.05, 1200.0), CurvePoint(0.1, 4500.0)),
            source_filename="loss.csv",
            extraction=None,
        ),
    )
    return MaterialRecord(
        ref=MaterialRef("Magnetics", "Kool Mu", "60"),
        revision_id="0123456789ab",
        status=MaterialStatus.DRAFT,
        created_at="2026-07-17T08:32:00+00:00",
        reviewed_by=None,
        approved_by=None,
        sources=sources,
        series=series,
        relative_permeability=60.0,
        steinmetz=SteinmetzFit(2.5, 1.4, 2.3, 0.01, 0.02),
        notes="Digitized from manufacturer data.",
    )


def test_full_material_record_round_trips() -> None:
    record = _record()

    document = material_record_to_json(record)

    assert material_record_from_json(document) == record
    assert document["revisionId"] == "0123456789ab"
    assert "revisionId" not in material_record_to_json(record, include_revision=False)
    assert document["series"][0]["conditions"]["frequencyHz"] is None  # type: ignore[index]
    assert document["series"][0]["extraction"]["xAxis"]["pixelA"] == 10.0  # type: ignore[index]


def test_material_record_json_is_byte_identical_and_exactly_formatted() -> None:
    first = material_record_json(_record())
    second = material_record_json(_record())

    assert first == second
    assert first.endswith("\n")
    assert not first.endswith("\n\n")
    assert first.startswith('{\n  "approvedBy": null,\n')


def test_revision_id_ignores_workflow_transitions_but_hashes_material_content() -> None:
    draft = _record()
    reviewed = review_record(draft, "reviewer@example.com")
    approved = approve_record(reviewed, "approver@example.com")
    changed_point = replace(
        draft.series[0],
        points=(*draft.series[0].points[:-1], CurvePoint(79.577471546, 0.2)),
    )
    changed = replace(draft, series=(changed_point, draft.series[1]))

    assert revision_id_for(draft) == revision_id_for(draft)
    assert revision_id_for(reviewed) == revision_id_for(draft)
    assert revision_id_for(approved) == revision_id_for(draft)
    assert revision_id_for(changed) != revision_id_for(draft)
    assert len(revision_id_for(draft)) == 12


def test_sha256_hex_uses_lowercase_hexadecimal() -> None:
    assert sha256_hex(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_points_csv_has_exact_lf_format_and_rounds_to_nine_places() -> None:
    series = replace(
        _record().series[0],
        points=(CurvePoint(1.1234567896, 2.0), CurvePoint(3.0, 4.0000000004)),
    )

    rendered = points_csv(series)

    assert rendered == "x,y\n1.12345679,2.0\n3.0,4.0\n"
    assert "\r" not in rendered
    assert parse_points_csv(rendered) == ((1.12345679, 2.0), (3.0, 4.0))


@pytest.mark.parametrize(
    "text",
    [
        "",
        "a,b\n1,2\n",
        "x,y\n",
        "x,y\n1\n",
        "x,y\n1,2,3\n",
        "x,y\none,2\n",
        "x,y\n1,nan\n",
        "x,y\n1,2\n\n",
    ],
)
def test_parse_points_csv_rejects_malformed_input(text: str) -> None:
    with pytest.raises(ValueError, match="CSV"):
        parse_points_csv(text)
