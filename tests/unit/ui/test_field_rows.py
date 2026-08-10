from __future__ import annotations

from inductor_designer.domain.project import RequestedOutput
from tests.unit.ui.test_result_rows import available, rows


def test_a_flux_density_renders_in_millitesla() -> None:
    row = rows(available(RequestedOutput.FLUX_DENSITY, "core.maximum", 0.32))[0]

    assert row["label"] == "Flux density (maximum)"
    assert row["text"].startswith("320")
    assert row["text"].endswith("mT")


def test_a_current_density_renders_in_amperes_per_square_millimetre() -> None:
    row = rows(
        available(RequestedOutput.CURRENT_DENSITY, "winding.w1.maximum", 3.5e6)
    )[0]

    assert "A/mm²" in row["text"]
    assert row["label"] == "Current density (w1.maximum)"


def test_the_worst_section_and_the_average_both_appear() -> None:
    labels = [
        row["label"]
        for row in rows(
            available(RequestedOutput.FLUX_DENSITY, "core.worst-section-mean", 0.31),
            available(RequestedOutput.FLUX_DENSITY, "core.area-weighted-average", 0.25),
        )
    ]

    assert labels == [
        "Flux density (worst-section-mean)",
        "Flux density (area-weighted-average)",
    ]


def test_per_section_rows_are_summarized_rather_than_listed() -> None:
    produced = rows(
        available(
            RequestedOutput.FLUX_DENSITY, "core.section.core.00.span-start", 0.31
        ),
        available(
            RequestedOutput.FLUX_DENSITY, "core.section.core.01.span-mid", 0.29
        ),
        available(RequestedOutput.FLUX_DENSITY, "core.maximum", 0.42),
    )

    labels = [row["label"] for row in produced]
    assert "Per-section detail" in labels
    assert not any("span-start" in label for label in labels)
    detail = next(row for row in produced if row["label"] == "Per-section detail")
    assert "2 evaluated sections" in detail["text"]
    assert "results.json" in detail["text"]


def test_no_section_pointer_without_sections() -> None:
    labels = [
        row["label"]
        for row in rows(available(RequestedOutput.FLUX_DENSITY, "core.maximum", 0.42))
    ]

    assert "Per-section detail" not in labels
