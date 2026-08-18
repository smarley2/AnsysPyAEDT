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
    assert advice.code == AdviceCode.LICENSE_CONFIGURATION_UNREADABLE


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


def test_cancellation_is_not_reported_as_a_failure() -> None:
    """Both cancellation wordings reach the advice table as failed stages."""
    for diagnostic in (
        "Run cancelled before stage 'analyze'.",
        "Run cancelled before the FEMM analysis.",
    ):
        advice = advise(diagnostic)
        assert advice.code == AdviceCode.RUN_CANCELLED
        assert advice.action == (
            "The run was cancelled on request; nothing failed. Start a new run "
            "when you are ready."
        )


def test_engine_detected_error_points_at_the_log_not_at_the_project_files() -> None:
    """AEDT's generic wrapper cannot name a cause, only where the cause is."""
    advice = advise("Engine Detected Error: out of memory during pass 3")
    assert advice.code == AdviceCode.SOLVER_STOPPED_EARLY
    assert advice.action == (
        "AEDT's solver stopped before finishing, so no reported value can be "
        "trusted. Its own reason is in this run's application log, on the "
        "`AEDT [analyze]:` lines. Common causes: a solver child process that "
        "could not start (check the AEDT installation and any antivirus "
        "blocking `ansysedt.exe`), an out-of-memory solve, or a licence lost "
        "mid-solve."
    )


def test_an_expired_licence_is_not_a_network_problem() -> None:
    advice = advise("FlexNet Licensing error:-10,32. Feature has expired.")
    assert advice.code == AdviceCode.LICENSE_EXPIRED
    assert advice.action == (
        "The Maxwell licence has expired. Ask the licence administrator for a "
        "current licence file, then run again."
    )


def test_exhausted_seats_are_not_a_network_problem() -> None:
    advice = advise(
        "FlexNet Licensing error:-4,132. All licenses in use: Licensed number "
        "of users already reached."
    )
    assert advice.code == AdviceCode.LICENSE_SEATS_EXHAUSTED
    assert advice.action == (
        "Every Maxwell licence seat is in use. Wait for a seat, or ask the "
        "licence administrator to free one, then run again."
    )


def test_an_unclassified_flexnet_error_says_where_the_number_is_read() -> None:
    advice = advise("FlexNet Licensing error:-97,121")
    assert advice.code == AdviceCode.LICENSE_FLEXNET_ERROR
    assert advice.action == (
        "AEDT reported a FlexNet licensing error. The error number in the text "
        "above identifies it; check the Ansys License Management Center, View "
        "Status, then run again."
    )


def test_an_unreadable_licence_file_is_a_configuration_problem() -> None:
    advice = advise("Cannot find license file.")
    assert advice.code == AdviceCode.LICENSE_CONFIGURATION_UNREADABLE
    assert advice.action == (
        "AEDT could not read its licence configuration. Open the Ansys License "
        "Management Center, confirm the licence server entry, then run the "
        "design again."
    )


def test_an_unreachable_licence_server_names_the_variable_and_the_ports() -> None:
    advice = advise("Cannot connect to license server system.")
    assert advice.code == AdviceCode.LICENSE_SERVER_UNREACHABLE
    assert advice.action == (
        "The licence server did not answer. Confirm `ANSYSLMD_LICENSE_FILE` "
        "points at the licence server and that ports 1055 and 2325 are "
        "reachable, then run again."
    )


def test_another_product_being_absent_is_not_read_as_a_missing_aedt() -> None:
    """`is not installed` blamed AEDT for anything, including FEMM."""
    assert advise("FEMM 4.2 is not installed on this machine").code == (
        AdviceCode.UNCLASSIFIED
    )


def test_missing_pyaedt_names_the_interpreter_that_has_to_get_it() -> None:
    advice = advise("No module named 'ansys.aedt.core'")
    assert ".venv/Scripts/python.exe -m pip install pyaedt" in advice.action


def test_denied_access_does_not_presume_a_write() -> None:
    expected = (
        "The application was denied access to that path. Check the folder's "
        "permissions, or choose a writable output folder, then start a new run."
    )
    assert advise("PermissionError: [Errno 13] Permission denied").action == expected
    assert advise("Access is denied.").action == expected


def test_a_material_mention_is_reported_as_a_mention_not_as_a_rejection() -> None:
    advice = advise("Reading material N87 from the project library")
    assert advice.code == AdviceCode.MATERIAL_REJECTED_BY_SOLVER
    assert advice.action == (
        "AEDT's message mentions a material. Check the pinned revision and its "
        "B-H series in Material Studio."
    )


def test_a_missed_target_is_named_only_when_there_is_a_target() -> None:
    with_target = convergence_advice(
        final_error_percent=4.0,
        target_percent=1.0,
        completed_passes=4,
        maximum_passes=10,
        converged=False,
    )
    assert with_target is not None
    assert "without meeting its 1 percent target" in with_target.action

    without_target = convergence_advice(
        final_error_percent=4.0,
        target_percent=None,
        completed_passes=4,
        maximum_passes=None,
        converged=False,
    )
    assert without_target is not None
    assert without_target.code == AdviceCode.CONVERGENCE_NOT_REACHED
    # No target exists, so none may be claimed.
    assert "target" not in without_target.action.split("relax the")[0]
    assert without_target.action.startswith(
        "The solve ended at 4 percent error. Treat the reported values as "
        "unconverged"
    )
