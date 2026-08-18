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
    LICENSE_SERVER_UNREACHABLE = "license.server_unreachable"
    MATERIAL_REJECTED_BY_SOLVER = "material.rejected_by_solver"
    FILE_PERMISSION_DENIED = "file.permission_denied"
    FILE_LOCKED = "file.locked"
    FILE_MISSING_SOLVER_DATA = "file.missing_solver_data"
    CONVERGENCE_NOT_REACHED = "convergence.not_reached"
    CONVERGENCE_PASS_LIMIT = "convergence.pass_limit_reached"
    UNCLASSIFIED = "run.unclassified_failure"


@dataclass(frozen=True, slots=True)
class FailureAdvice:
    code: str
    action: str


# First match wins, so the more specific subject is listed first. A licence
# file that cannot be opened is a licence problem, not a file problem.
_RULES: tuple[tuple[str, str, str], ...] = (
    (
        "license file",
        AdviceCode.LICENSE_UNAVAILABLE,
        "AEDT could not read its licence configuration. Open Ansys License "
        "Settings, confirm the licence server entry, and run the design again.",
    ),
    (
        "license server",
        AdviceCode.LICENSE_SERVER_UNREACHABLE,
        "The licence server did not answer. Confirm network access to the "
        "Ansys licence server, then run the design again.",
    ),
    (
        "flexnet",
        AdviceCode.LICENSE_SERVER_UNREACHABLE,
        "The licence server did not answer. Confirm network access to the "
        "Ansys licence server, then run the design again.",
    ),
    (
        "no license available",
        AdviceCode.LICENSE_UNAVAILABLE,
        "No Maxwell licence was free. Wait for a licence to be released, or "
        "ask the licence administrator, then run the design again.",
    ),
    (
        "license",
        AdviceCode.LICENSE_UNAVAILABLE,
        "AEDT reported a licensing problem. Check the Ansys licence status, "
        "then run the design again.",
    ),
    (
        "no module named 'ansys",
        AdviceCode.INSTALLATION_PYAEDT_MISSING,
        "PyAEDT is not installed in this interpreter. Install it with "
        "`pip install pyaedt` into the same environment that runs the "
        "application.",
    ),
    (
        "no module named 'femm",
        AdviceCode.INSTALLATION_FEMM_MISSING,
        "pyFEMM is not installed, or FEMM 4.2 is not present. Install FEMM "
        "4.2 and `pip install pyfemm`, or choose a Maxwell backend.",
    ),
    (
        "is not installed",
        AdviceCode.INSTALLATION_AEDT_NOT_REACHABLE,
        "AEDT 2025 R2 Commercial was not found. Install it, or select a "
        "backend that does not need it.",
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
        "engine detected error",
        AdviceCode.FILE_MISSING_SOLVER_DATA,
        "The AEDT solver engine rejected the project files. Start a new run "
        "rather than solving this directory again.",
    ),
    (
        "being used",
        AdviceCode.FILE_LOCKED,
        "Another program holds the file. Close AEDT, FEMM or the file "
        "explorer that has it open, then start a new run.",
    ),
    (
        "permission denied",
        AdviceCode.FILE_PERMISSION_DENIED,
        "The application may not write there. Save the project into a "
        "writable folder, then start a new run.",
    ),
    (
        "access is denied",
        AdviceCode.FILE_PERMISSION_DENIED,
        "The application may not write there. Save the project into a "
        "writable folder, then start a new run.",
    ),
    (
        "permeability",
        AdviceCode.MATERIAL_REJECTED_BY_SOLVER,
        "The solver rejected the pinned material data. Open Material Studio, "
        "confirm the B-H series for the requested temperature, and pin a "
        "revision the solver accepts.",
    ),
    (
        "material",
        AdviceCode.MATERIAL_REJECTED_BY_SOLVER,
        "The solver rejected the pinned material. Open Material Studio and "
        "confirm the pinned revision and its B-H series.",
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
    return FailureAdvice(
        code=AdviceCode.CONVERGENCE_NOT_REACHED,
        action=(
            f"The solve ended at {final_error_percent:g} percent error "
            "without meeting its target. Treat the reported values as "
            "unconverged, refine the mesh intent or relax the target, then "
            "run again."
        ),
    )
