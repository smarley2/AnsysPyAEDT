"""What to do about a failure, keyed on the text the solver actually produced.

Advice is always appended to the raw diagnostic, never substituted for it: the
raw text is the evidence and the advice is the reading of it. Text nobody has
classified yet returns `run.unclassified_failure`, which says so honestly
rather than guessing.

The match substrings below are the observed wording of AEDT 2025 R2, pyFEMM
4.2 and the Python standard library as of 2026-08-18. A substring that stops
matching costs the advice line, never the diagnostic, so a wrong entry here
cannot turn a failure into a success.
"""

from __future__ import annotations

from dataclasses import dataclass


class AdviceCode:
    """Stable lowercase dotted `<subject>.<reason>` advice codes."""

    INSTALLATION_PYAEDT_MISSING = "installation.pyaedt_missing"
    INSTALLATION_FEMM_MISSING = "installation.femm_missing"
    INSTALLATION_AEDT_NOT_REACHABLE = "installation.aedt_not_reachable"
    LICENSE_UNAVAILABLE = "license.unavailable"
    LICENSE_SEATS_EXHAUSTED = "license.seats_exhausted"
    LICENSE_EXPIRED = "license.expired"
    LICENSE_CONFIGURATION_UNREADABLE = "license.configuration_unreadable"
    LICENSE_FLEXNET_ERROR = "license.flexnet_error"
    LICENSE_SERVER_UNREACHABLE = "license.server_unreachable"
    MATERIAL_REJECTED_BY_SOLVER = "material.rejected_by_solver"
    FILE_PERMISSION_DENIED = "file.permission_denied"
    FILE_LOCKED = "file.locked"
    FILE_MISSING_SOLVER_DATA = "file.missing_solver_data"
    SOLVER_STOPPED_EARLY = "solver.stopped_early"
    CONVERGENCE_NOT_REACHED = "convergence.not_reached"
    CONVERGENCE_PASS_LIMIT = "convergence.pass_limit_reached"
    RUN_CANCELLED = "run.cancelled"
    UNCLASSIFIED = "run.unclassified_failure"


@dataclass(frozen=True, slots=True)
class FailureAdvice:
    code: str
    action: str


_DENIED_ACTION = (
    "The application was denied access to that path. Check the folder's "
    "permissions, or choose a writable output folder, then start a new run."
)

# First match wins, so the more specific subject is listed first. A licence
# file that cannot be opened is a licence problem, not a file problem.
_RULES: tuple[tuple[str, str, str], ...] = (
    (
        # A cancellation is recorded as an unsuccessful stage, so it reaches the
        # advice table. It is not a failure and must not be reported as one.
        "run cancelled",
        AdviceCode.RUN_CANCELLED,
        "The run was cancelled on request; nothing failed. Start a new run "
        "when you are ready.",
    ),
    (
        # Ansys prints "FlexNet Licensing error:" on nearly every licence
        # failure, so the specific reasons must be read before that wrapper.
        "licensed number of users",
        AdviceCode.LICENSE_SEATS_EXHAUSTED,
        "Every Maxwell licence seat is in use. Wait for a seat, or ask the "
        "licence administrator to free one, then run again.",
    ),
    (
        "has expired",
        AdviceCode.LICENSE_EXPIRED,
        "The Maxwell licence has expired. Ask the licence administrator for a "
        "current licence file, then run again.",
    ),
    (
        "no license available",
        AdviceCode.LICENSE_UNAVAILABLE,
        "No Maxwell licence was free. Wait for a licence to be released, or "
        "ask the licence administrator, then run the design again.",
    ),
    (
        "license file",
        AdviceCode.LICENSE_CONFIGURATION_UNREADABLE,
        "AEDT could not read its licence configuration. Open the Ansys License "
        "Management Center, confirm the licence server entry, then run the "
        "design again.",
    ),
    (
        "license server",
        AdviceCode.LICENSE_SERVER_UNREACHABLE,
        "The licence server did not answer. Confirm `ANSYSLMD_LICENSE_FILE` "
        "points at the licence server and that ports 1055 and 2325 are "
        "reachable, then run again.",
    ),
    (
        "flexnet",
        AdviceCode.LICENSE_FLEXNET_ERROR,
        "AEDT reported a FlexNet licensing error. The error number in the text "
        "above identifies it; check the Ansys License Management Center, View "
        "Status, then run again.",
    ),
    (
        "license",
        AdviceCode.LICENSE_UNAVAILABLE,
        "AEDT reported a licensing problem. Check the Ansys License Management "
        "Center, then run the design again.",
    ),
    (
        "no module named 'ansys",
        AdviceCode.INSTALLATION_PYAEDT_MISSING,
        "PyAEDT is not installed in this interpreter. Install it with "
        "`.venv/Scripts/python.exe -m pip install pyaedt`, into the same "
        "environment that runs the application.",
    ),
    (
        "no module named 'femm",
        AdviceCode.INSTALLATION_FEMM_MISSING,
        "pyFEMM is not installed, or FEMM 4.2 is not present. Install FEMM "
        "4.2 and `pip install pyfemm`, or choose a Maxwell backend.",
    ),
    (
        "failed to connect",
        AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE,
        "The application could not reach an AEDT session. Close any AEDT "
        "window and any leftover ansysedt.exe process, then run again: only "
        "one AEDT session may be active.",
    ),
    (
        "desktop is not running",
        AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE,
        "The AEDT desktop stopped before the run finished. Close any leftover "
        "ansysedt.exe process and start a new run.",
    ),
    (
        ".adp",
        AdviceCode.FILE_MISSING_SOLVER_DATA,
        "AEDT could not read the solver data of this project. A run directory "
        "written by an interrupted session cannot be solved again in place: "
        "start a new run, which gets its own directory.",
    ),
    (
        # "Engine Detected Error" is AEDT's generic wrapper for any solver-side
        # death, so it can only point at where the real reason was written.
        "engine detected error",
        AdviceCode.SOLVER_STOPPED_EARLY,
        "AEDT's solver stopped before finishing, so no reported value can be "
        "trusted. Its own reason is in this run's application log, on the "
        "`AEDT [analyze]:` lines. Common causes: a solver child process that "
        "could not start (check the AEDT installation and any antivirus "
        "blocking `ansysedt.exe`), an out-of-memory solve, or a licence lost "
        "mid-solve.",
    ),
    (
        "being used",
        AdviceCode.FILE_LOCKED,
        "Another program holds the file. Close AEDT, FEMM or the file "
        "explorer that has it open, then start a new run.",
    ),
    (
        # Reads and refused COM calls produce this too, so it cannot presume a
        # write.
        "permission denied",
        AdviceCode.FILE_PERMISSION_DENIED,
        _DENIED_ACTION,
    ),
    (
        "access is denied",
        AdviceCode.FILE_PERMISSION_DENIED,
        _DENIED_ACTION,
    ),
    (
        "permeability",
        AdviceCode.MATERIAL_REJECTED_BY_SOLVER,
        "The solver rejected the pinned material data. Open Material Studio, "
        "confirm the B-H series for the requested temperature, and pin a "
        "revision the solver accepts.",
    ),
    (
        # Any text containing the word matches, which is not enough to claim the
        # solver rejected anything. It can only point, not conclude.
        "material",
        AdviceCode.MATERIAL_REJECTED_BY_SOLVER,
        "AEDT's message mentions a material. Check the pinned revision and its "
        "B-H series in Material Studio.",
    ),
)

_UNCLASSIFIED_ACTION = (
    "The failure text is not one this application recognises. Keep the run "
    "directory and attach a diagnostic bundle when reporting it."
)


def advise(diagnostic: str) -> FailureAdvice:
    """The action for one raw diagnostic. Never raises, never returns None."""
    lowered = diagnostic.casefold()
    for needle, code, action in _RULES:
        if needle in lowered:
            return FailureAdvice(code=code, action=action)
    return FailureAdvice(code=AdviceCode.UNCLASSIFIED, action=_UNCLASSIFIED_ACTION)


def convergence_advice(
    *,
    final_error_percent: float,
    target_percent: float | None,
    completed_passes: int,
    maximum_passes: int | None,
    converged: bool | None,
) -> FailureAdvice | None:
    """Advice for a solve that finished without meeting its own target.

    Returns None when the solve converged, or when neither a target nor a
    reported state supports any claim: an unproven "did not converge" would be
    a worse diagnostic than silence.
    """
    if converged is True:
        return None
    target_missed = target_percent is not None and final_error_percent > target_percent
    if not target_missed and converged is not False:
        return None
    if maximum_passes is not None and completed_passes >= maximum_passes:
        return FailureAdvice(
            code=AdviceCode.CONVERGENCE_PASS_LIMIT,
            action=(
                f"The solve used all {maximum_passes} adaptive passes and "
                f"ended at {final_error_percent:g} percent error. Raise the "
                "maximum passes, relax the percent error target, or refine "
                "the mesh intent, then run again."
            ),
        )
    # Only a target that exists and was missed may be named: with no target the
    # sentence would invent one, and AEDT's own "did not converge" stands alone.
    missed = f" without meeting its {target_percent:g} percent target" if target_missed else ""
    return FailureAdvice(
        code=AdviceCode.CONVERGENCE_NOT_REACHED,
        action=(
            f"The solve ended at {final_error_percent:g} percent error"
            f"{missed}. Treat the reported values as unconverged, refine the "
            "mesh intent or relax the target, then run again."
        ),
    )
