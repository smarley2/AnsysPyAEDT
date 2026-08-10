"""The per-run result files written beside the solve log.

JSON reuses the manifest's own result document, so an exported file and the
manifest can never describe the same run differently. CSV is the tabular view
of the same rows, unavailable entries included: a reader must be able to see
what was asked for and did not come back.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from inductor_designer.simulation.run_contracts import (
    ComplexValue,
    MatrixValue,
    NormalizedResultSet,
    NormalizedValue,
)

RESULTS_JSON_FILENAME = "results.json"
RESULTS_CSV_FILENAME = "results.csv"
RESULTS_JSON_ARTIFACT_KIND = "results-json"
RESULTS_CSV_ARTIFACT_KIND = "results-csv"

CSV_COLUMNS: tuple[str, ...] = (
    "quantity",
    "scope",
    "availability",
    "value",
    "unit",
    "currentConvention",
    "approximation",
    "reason",
    "provenance",
)


def _csv_value(value: NormalizedValue | None) -> str:
    if value is None:
        return ""
    if isinstance(value, ComplexValue):
        return f"{value.real:g}{value.imaginary:+g}j"
    if isinstance(value, MatrixValue):
        # A matrix does not fit one cell; the JSON export carries it in full.
        return f"matrix {len(value.row_labels)}x{len(value.column_labels)}"
    return f"{value:g}"


def results_csv_text(results: NormalizedResultSet) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for quantity in results.quantities:
        writer.writerow(
            {
                "quantity": quantity.quantity.value,
                "scope": quantity.scope,
                "availability": quantity.availability.value,
                "value": _csv_value(quantity.value),
                "unit": quantity.unit or "",
                "currentConvention": quantity.current_convention.value,
                "approximation": quantity.approximation or "",
                "reason": quantity.reason or "",
                "provenance": quantity.provenance or "",
            }
        )
    return buffer.getvalue()


def write_result_files(
    results_directory: Path, results: NormalizedResultSet
) -> tuple[Path, Path]:
    from inductor_designer.application.services.maxwell_export import (
        results_to_document,
    )

    results_directory.mkdir(parents=True, exist_ok=True)
    json_path = results_directory / RESULTS_JSON_FILENAME
    json_path.write_text(
        json.dumps(results_to_document(results), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    csv_path = results_directory / RESULTS_CSV_FILENAME
    csv_path.write_text(results_csv_text(results), encoding="utf-8")
    return json_path, csv_path
