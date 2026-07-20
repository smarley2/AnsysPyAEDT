from __future__ import annotations

from dataclasses import replace

import pytest

from inductor_designer.application.services.material_import import MaterialImportError
from inductor_designer.application.services.material_table_import import (
    MaterialTableMetadata,
    MaterialTableRow,
    import_material_rows,
)
from inductor_designer.materials.identity import MaterialRef
from inductor_designer.materials.records import (
    CurveConditions,
    CurvePoint,
    SeriesKind,
    SourceKind,
)
from inductor_designer.materials.serde import sha256_hex


def _metadata() -> MaterialTableMetadata:
    return MaterialTableMetadata(
        ref=MaterialRef("Example", "Ferrite", "F1"),
        source_url="https://example.com/f1",
        source_page=7,
        captured_at="2026-07-18T12:00:00+00:00",
        source_description="Example multi-series table",
    )


def test_import_material_rows_groups_series_and_preserves_replay_sources() -> None:
    rows = (
        MaterialTableRow("bh-25c", SeriesKind.BH_CURVE, None, 25.0, None, "Oe", "kG", 1.0, 1.0),
        MaterialTableRow("bh-100c", SeriesKind.BH_CURVE, None, 100.0, None, "A/m", "T", 1.0, 0.001),
        MaterialTableRow("bh-25c", SeriesKind.BH_CURVE, None, 25.0, None, "Oe", "kG", 0.0, 0.0),
        MaterialTableRow(
            "loss-100khz", SeriesKind.LOSS_TABLE, 100_000.0, 25.0, 0.0, "kG", "mW/cm3", 2.0, 3.0
        ),
        MaterialTableRow(
            "loss-200khz", SeriesKind.LOSS_TABLE, 200_000.0, 100.0, 10.0, "T", "W/m3", 0.2, 4000.0
        ),
        MaterialTableRow("bh-100c", SeriesKind.BH_CURVE, None, 100.0, None, "A/m", "T", 0.0, 0.0),
        MaterialTableRow(
            "loss-100khz", SeriesKind.LOSS_TABLE, 100_000.0, 25.0, 0.0, "kG", "mW/cm3", 1.0, 1.0
        ),
        MaterialTableRow(
            "loss-200khz", SeriesKind.LOSS_TABLE, 200_000.0, 100.0, 10.0, "T", "W/m3", 0.1, 1000.0
        ),
    )

    result = import_material_rows(
        _metadata(),
        rows,
        upload_filename="material.xlsx",
        upload_kind=SourceKind.SPREADSHEET,
        upload_bytes=b"workbook",
    )

    assert result.ref == _metadata().ref
    assert tuple(series.series_id for series in result.series) == (
        "bh-25c",
        "bh-100c",
        "loss-100khz",
        "loss-200khz",
    )
    assert result.series[0].points == (
        CurvePoint(0.0, 0.0),
        CurvePoint(79.577471546, 0.1),
    )
    assert result.series[0].conditions == CurveConditions(None, 25.0, None)
    assert result.series[1].conditions == CurveConditions(None, 100.0, None)
    assert result.series[2].points == (
        CurvePoint(0.1, 1000.0),
        CurvePoint(0.2, 3000.0),
    )
    assert result.series[2].conditions == CurveConditions(100_000.0, 25.0, 0.0)
    assert result.series[3].conditions == CurveConditions(200_000.0, 100.0, 10.0)

    assert tuple(source.filename for source in result.sources) == (
        "material.xlsx",
        "series-bh_25c.csv",
        "series-bh_100c.csv",
        "series-loss_100khz.csv",
        "series-loss_200khz.csv",
    )
    source_files = dict(result.source_files)
    assert source_files["material.xlsx"] == b"workbook"
    assert source_files["series-bh_25c.csv"] == b"x,y\n1.0,1.0\n0.0,0.0\n"
    assert result.sources[0].sha256 == sha256_hex(b"workbook")
    assert all(
        source.sha256 == sha256_hex(source_files[source.filename]) for source in result.sources[1:]
    )
    assert all(source.url == "" for source in result.sources[1:])
    assert all(source.page is None for source in result.sources[1:])
    assert all(
        source.description == "Material Studio generated per-series CSV"
        for source in result.sources[1:]
    )
    assert tuple(series.source_filename for series in result.series) == tuple(
        source.filename for source in result.sources[1:]
    )


def _bh_row(series_id: str = "bh") -> MaterialTableRow:
    return MaterialTableRow(
        series_id,
        SeriesKind.BH_CURVE,
        None,
        25.0,
        None,
        "A/m",
        "T",
        0.0,
        0.0,
    )


def _import(rows: tuple[MaterialTableRow, ...]) -> None:
    import_material_rows(
        _metadata(),
        rows,
        upload_filename="material.xlsx",
        upload_kind=SourceKind.SPREADSHEET,
        upload_bytes=b"workbook",
    )


def test_import_material_rows_rejects_empty_input() -> None:
    with pytest.raises(MaterialImportError) as caught:
        _import(())

    assert caught.value.issues == ("material table requires at least one data row",)


def test_import_material_rows_rejects_blank_series_id() -> None:
    with pytest.raises(MaterialImportError) as caught:
        _import((_bh_row("  "),))

    assert caught.value.issues == ("row 1 series_id must not be blank",)


@pytest.mark.parametrize(
    ("changed", "expected_field"),
    [
        ({"kind": SeriesKind.LOSS_TABLE}, "kind"),
        ({"frequency_hz": 100_000.0}, "frequency_hz"),
        ({"temperature_c": 100.0}, "temperature_c"),
        ({"dc_bias_a_per_m": 10.0}, "dc_bias_a_per_m"),
        ({"x_unit": "Oe"}, "x_unit"),
        ({"y_unit": "G"}, "y_unit"),
    ],
)
def test_import_material_rows_rejects_mixed_series_metadata(
    changed: dict[str, object], expected_field: str
) -> None:
    first = _bh_row()

    with pytest.raises(MaterialImportError) as caught:
        _import((first, replace(first, x=1.0, y=1.0, **changed)))

    assert caught.value.issues == (f"series 'bh' has inconsistent {expected_field}",)


def test_import_material_rows_rejects_generated_filename_collision() -> None:
    with pytest.raises(MaterialImportError) as caught:
        _import((_bh_row("a-b"), _bh_row("a b")))

    assert caught.value.issues == (
        "series IDs 'a-b' and 'a b' generate the same source filename 'series-a_b.csv'",
    )


def test_import_material_rows_rejects_generated_filename_matching_upload() -> None:
    with pytest.raises(MaterialImportError) as caught:
        import_material_rows(
            _metadata(),
            (_bh_row(),),
            upload_filename="series-bh.csv",
            upload_kind=SourceKind.CSV,
            upload_bytes=b"upload",
        )

    assert caught.value.issues == (
        "generated source filename 'series-bh.csv' conflicts with upload filename",
    )


def test_import_material_rows_rejects_case_insensitive_generated_filename_collision() -> None:
    with pytest.raises(MaterialImportError) as caught:
        _import((_bh_row("BH"), _bh_row("bh")))

    assert caught.value.issues == (
        "series IDs 'BH' and 'bh' generate the same source filename 'series-bh.csv'",
    )


def test_import_material_rows_rejects_case_insensitive_upload_filename_collision() -> None:
    with pytest.raises(MaterialImportError) as caught:
        import_material_rows(
            _metadata(),
            (_bh_row("bh"),),
            upload_filename="series-BH.csv",
            upload_kind=SourceKind.CSV,
            upload_bytes=b"upload",
        )

    assert caught.value.issues == (
        "generated source filename 'series-bh.csv' conflicts with upload filename",
    )


def test_import_material_rows_rejects_unsupported_upload_kind() -> None:
    with pytest.raises(MaterialImportError) as caught:
        import_material_rows(
            _metadata(),
            (_bh_row(),),
            upload_filename="material.png",
            upload_kind="image",  # type: ignore[arg-type]
            upload_bytes=b"image",
        )

    assert caught.value.issues == ("upload kind must be csv or spreadsheet",)
