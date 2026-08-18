from __future__ import annotations

from inductor_designer.simulation.failure_advice import (
    AdviceCode,
    advise,
    convergence_advice,
)


def test_missing_pyaedt_is_an_installation_problem() -> None:
    advice = advise("No module named 'ansys.aedt.core'")
    assert advice.code == AdviceCode.INSTALLATION_PYAEDT_MISSING
    assert "pip install" in advice.action


def test_missing_femm_is_an_installation_problem() -> None:
    advice = advise("No module named 'femm'")
    assert advice.code == AdviceCode.INSTALLATION_FEMM_MISSING


def test_unreachable_desktop_is_an_installation_problem() -> None:
    advice = advise("Failed to connect to AEDT: Desktop is not running.")
    assert advice.code == AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE


def test_license_text_is_a_license_problem() -> None:
    advice = advise("License checkout failed: no license available for Maxwell")
    assert advice.code == AdviceCode.LICENSE_UNAVAILABLE


def test_flexlm_server_text_names_the_licence_server() -> None:
    advice = advise("FlexNet error -15: cannot connect to license server")
    assert advice.code == AdviceCode.LICENSE_SERVER_UNREACHABLE


def test_missing_solver_data_file_names_the_never_re_solve_rule() -> None:
    advice = advise(
        "Engine Detected Error: Failed to open project file model.adp"
    )
    assert advice.code == AdviceCode.FILE_MISSING_SOLVER_DATA
    assert "new run" in advice.action.casefold()


def test_locked_file_is_a_file_problem() -> None:
    advice = advise("The process cannot access the file because it is being used")
    assert advice.code == AdviceCode.FILE_LOCKED


def test_denied_file_is_a_file_problem() -> None:
    advice = advise("PermissionError: [Errno 13] Permission denied")
    assert advice.code == AdviceCode.FILE_PERMISSION_DENIED


def test_material_text_is_a_material_problem() -> None:
    advice = advise("Invalid permeability dataset for material N87")
    assert advice.code == AdviceCode.MATERIAL_REJECTED_BY_SOLVER


def test_unrecognised_text_is_honestly_unclassified() -> None:
    advice = advise("something nobody has seen before")
    assert advice.code == AdviceCode.UNCLASSIFIED
    assert advice.action


def test_first_match_wins_so_a_licence_file_error_is_a_licence_error() -> None:
    advice = advise("Cannot open license file: permission denied")
    assert advice.code == AdviceCode.LICENSE_UNAVAILABLE


def test_a_converged_run_needs_no_convergence_advice() -> None:
    assert (
        convergence_advice(
            final_error_percent=0.4,
            target_percent=1.0,
            completed_passes=3,
            maximum_passes=10,
            converged=True,
        )
        is None
    )


def test_pass_limit_advice_when_the_solver_ran_out_of_passes() -> None:
    advice = convergence_advice(
        final_error_percent=4.0,
        target_percent=1.0,
        completed_passes=10,
        maximum_passes=10,
        converged=False,
    )
    assert advice is not None
    assert advice.code == AdviceCode.CONVERGENCE_PASS_LIMIT


def test_target_missed_advice_when_passes_remained() -> None:
    advice = convergence_advice(
        final_error_percent=4.0,
        target_percent=1.0,
        completed_passes=4,
        maximum_passes=10,
        converged=False,
    )
    assert advice is not None
    assert advice.code == AdviceCode.CONVERGENCE_NOT_REACHED


def test_no_target_and_no_state_produces_no_claim() -> None:
    assert (
        convergence_advice(
            final_error_percent=4.0,
            target_percent=None,
            completed_passes=4,
            maximum_passes=None,
            converged=None,
        )
        is None
    )
