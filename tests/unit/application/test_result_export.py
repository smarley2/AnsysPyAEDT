from __future__ import annotations

import csv
import json
from pathlib import Path

from inductor_designer.application.services.result_export import write_result_files
from inductor_designer.domain.project import RequestedOutput
from inductor_designer.simulation.run_contracts import (
    CurrentConvention,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
    RunBackend,
)

RESULTS = NormalizedResultSet(
    run_id="20260810-120000",
    backend=RunBackend.FEMM,
    quantities=(
        NormalizedQuantity(
            quantity=RequestedOutput.RESISTANCE,
            scope="winding.w1",
            availability=ResultAvailability.AVAILABLE,
            value=0.125,
            unit="ohm",
            current_convention=CurrentConvention.NOT_APPLICABLE,
            approximation=None,
            reason=None,
            provenance="FEMM circuit properties",
        ),
        NormalizedQuantity(
            quantity=RequestedOutput.CORE_LOSS,
            scope="device",
            availability=ResultAvailability.UNAVAILABLE,
            value=None,
            unit=None,
            current_convention=CurrentConvention.AC_RMS,
            approximation=None,
            reason="core-loss.not_reported: FEMM does not report a core loss.",
            provenance=None,
        ),
    ),
)


def test_both_files_land_in_the_results_directory(tmp_path: Path) -> None:
    json_path, csv_path = write_result_files(tmp_path, RESULTS)

    assert json_path == tmp_path / "results.json"
    assert csv_path == tmp_path / "results.csv"


def test_the_json_carries_the_full_provenance(tmp_path: Path) -> None:
    json_path, _ = write_result_files(tmp_path, RESULTS)

    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["runId"] == "20260810-120000"
    assert document["backend"] == "femm"
    assert document["quantities"][0]["provenance"] == "FEMM circuit properties"


def test_the_csv_keeps_one_row_per_quantity_including_unavailable_ones(
    tmp_path: Path,
) -> None:
    _, csv_path = write_result_files(tmp_path, RESULTS)

    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))
    assert [row["quantity"] for row in rows] == ["resistance", "core-loss"]
    assert rows[0]["value"] == "0.125"
    assert rows[1]["value"] == ""
    assert rows[1]["reason"].startswith("core-loss.not_reported")


def test_the_csv_header_is_stable(tmp_path: Path) -> None:
    _, csv_path = write_result_files(tmp_path, RESULTS)

    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == (
        "quantity,scope,availability,value,unit,currentConvention,"
        "approximation,reason,provenance"
    )


def test_a_complex_value_keeps_both_parts_in_the_csv(tmp_path: Path) -> None:
    from inductor_designer.simulation.run_contracts import ComplexValue

    results = NormalizedResultSet(
        run_id="r",
        backend=RunBackend.FEMM,
        quantities=(
            NormalizedQuantity(
                quantity=RequestedOutput.IMPEDANCE,
                scope="winding.w1",
                availability=ResultAvailability.AVAILABLE,
                value=ComplexValue(real=0.1, imaginary=3.2),
                unit="ohm",
                current_convention=CurrentConvention.NOT_APPLICABLE,
                approximation=None,
                reason=None,
                provenance="FEMM circuit properties",
            ),
        ),
    )

    _, csv_path = write_result_files(tmp_path, results)

    row = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))[0]
    assert row["value"] == "0.1+3.2j"
