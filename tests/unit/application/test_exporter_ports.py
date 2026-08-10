from __future__ import annotations

from pathlib import Path

from inductor_designer.application.ports.femm_solver import FemmSolveRequest
from inductor_designer.application.ports.maxwell2d_exporter import (
    SOLVE_STAGE_NAMES_2D,
    STAGE_NAMES_2D,
    Maxwell2dExportRequest,
)
from inductor_designer.application.ports.maxwell_exporter import (
    SOLVE_STAGE_NAMES,
    STAGE_NAMES,
    Maxwell3dExportRequest,
)
from inductor_designer.domain.aedt_target import AedtEdition, AedtRelease


def test_solve_stage_names_append_analyze_to_the_generate_sequence() -> None:
    assert SOLVE_STAGE_NAMES == STAGE_NAMES + ("analyze",)
    assert SOLVE_STAGE_NAMES_2D == STAGE_NAMES_2D + ("analyze",)


def test_generate_sequences_still_end_with_save() -> None:
    assert STAGE_NAMES[-1] == "save"
    assert STAGE_NAMES_2D[-1] == "save"


def test_maxwell3d_request_defaults_to_generate_only(tmp_path: Path) -> None:
    request = Maxwell3dExportRequest(
        plan=None,  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="x",
    )
    assert request.solve is False
    assert request.progress is None
    assert request.cancellation is None


def test_maxwell2d_request_defaults_to_generate_only(tmp_path: Path) -> None:
    request = Maxwell2dExportRequest(
        plan=None,  # type: ignore[arg-type]
        release=AedtRelease(2025, 2),
        edition=AedtEdition.COMMERCIAL,
        non_graphical=True,
        output_directory=tmp_path,
        project_name="x",
    )
    assert request.solve is False
    assert request.progress is None
    assert request.cancellation is None


def test_femm_request_carries_progress_and_cancellation(tmp_path: Path) -> None:
    request = FemmSolveRequest(
        problem=None,  # type: ignore[arg-type]
        output_directory=tmp_path,
        project_name="x",
        analyze=False,
    )
    assert request.progress is None
    assert request.cancellation is None
