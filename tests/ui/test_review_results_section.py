from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtGui import QGuiApplication  # noqa: E402

from inductor_designer.domain.project import RequestedOutput  # noqa: E402
from inductor_designer.simulation.run_contracts import (  # noqa: E402
    CurrentConvention,
    NormalizedQuantity,
    NormalizedResultSet,
    ResultAvailability,
    RunBackend,
)
from inductor_designer.ui.generation_controller import GenerationController  # noqa: E402
from inductor_designer.ui.generation_lines import GenerationResult  # noqa: E402
from inductor_designer.ui.preliminary_controller import PreliminaryController  # noqa: E402
from inductor_designer.ui.project_session import ProjectSession  # noqa: E402
from inductor_designer.ui.review_controller import ReviewController  # noqa: E402
from tests.ui.conftest import wait_until_idle  # noqa: E402
from tests.unit.application.test_geometry_model import CATALOG  # noqa: E402
from tests.unit.domain.test_project import make_project  # noqa: E402

pytestmark = pytest.mark.ui

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


class _NoOpener:
    def open_path(self, path: Path) -> bool:
        return True


def build(
    results: NormalizedResultSet | None,
) -> tuple[QGuiApplication, ReviewController, GenerationController]:
    app = QGuiApplication.instance() or QGuiApplication([])
    generation = GenerationController(
        lambda _request: GenerationResult(("done",), result_set=results)
    )
    session = ProjectSession(make_project(), Path("boost.inductor.json"), lambda p: None)
    preliminary = PreliminaryController(session, CATALOG)
    review = ReviewController(session, preliminary, generation, CATALOG, _NoOpener())
    return app, review, generation


def sections(review: ReviewController) -> list[dict[str, object]]:
    return review.sections  # type: ignore[return-value]


def results_rows(review: ReviewController) -> list[dict[str, str]]:
    return next(
        section["rows"]  # type: ignore[return-value]
        for section in sections(review)
        if section["title"] == "Results"
    )


def test_no_results_section_before_any_solved_run() -> None:
    _, review, _ = build(None)

    assert "Results" not in [section["title"] for section in sections(review)]


def test_the_results_section_appears_after_a_solved_run() -> None:
    app, review, generation = build(RESULTS)

    generation.generate("FEMM 2D", False, True)
    wait_until_idle(app, generation)

    assert "Results" in [section["title"] for section in sections(review)]


def test_an_available_quantity_shows_its_value_and_unit() -> None:
    app, review, generation = build(RESULTS)

    generation.generate("FEMM 2D", False, True)
    wait_until_idle(app, generation)

    resistance = next(
        row for row in results_rows(review) if row["label"].startswith("Resistance")
    )
    assert "mΩ" in resistance["text"]


def test_an_unavailable_quantity_shows_its_reason_not_a_blank() -> None:
    app, review, generation = build(RESULTS)

    generation.generate("FEMM 2D", False, True)
    wait_until_idle(app, generation)

    core_loss = next(
        row for row in results_rows(review) if row["label"].startswith("Core loss")
    )
    assert core_loss["text"].startswith("core-loss.not_reported")


def test_the_results_section_comes_after_the_run_request() -> None:
    app, review, generation = build(RESULTS)

    generation.generate("FEMM 2D", False, True)
    wait_until_idle(app, generation)

    titles = [section["title"] for section in sections(review)]
    assert titles.index("Results") == len(titles) - 1


def test_review_states_whether_the_core_and_conductor_data_was_reviewed() -> None:
    """Review is where a run's provenance is reported. A `draft` core or wire
    is a number nobody has checked against the cited source page, and a
    reviewer reading this page has no other way to learn that -- the numbers
    themselves look identical either way."""
    _app, review, _generation = build(None)
    sections = {section["title"]: section["rows"] for section in review.sections}

    core_text = " ".join(row["text"] for row in sections["Core and material"])
    assert "reviewed" in core_text or "draft" in core_text

    winding_text = " ".join(row["text"] for row in sections["Winding excitations"])
    assert "draft" in winding_text or "reviewed" in winding_text
