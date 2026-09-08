"""Whether the solver stack this build ships can actually be imported.

Known risk 2 of the M10 release record: PyAEDT has only ever been exercised
from source. A frozen Qt/PyAEDT bundle fails in two ways a source run cannot
reveal -- a lazily imported module PyInstaller never saw, and a data file the
library reads off disk that was never collected -- and both surface as a
traceback mid-run, after the user has already built a design.

Both are import-time facts, so both can be checked with no AEDT session, no
license and no solve. That is deliberately all this does: it answers "is the
stack present and complete in this build", not "does a solve work". A solve
still needs AEDT, on a machine that has it.

The module list is the load-bearing part. Every lazily imported solver module
in `adapters/pyaedt/` and `adapters/femm/` belongs here, because a module
missing from this list is one whose absence the bundle discovers in front of
a user.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass

#: Every module the solver adapters import lazily, in the order a run reaches
#: them. `femm` is optional by design (the release notes say so); its absence
#: is a line in the report, not a failure.
_MODULES: tuple[tuple[str, bool], ...] = (
    ("ansys.aedt.core", False),
    ("ansys.aedt.core.modules.boundary.maxwell_boundary", False),
    ("ansys.aedt.core.internal.desktop_sessions", False),
    ("femm", True),
)

#: PyAEDT reads this off disk on every result read (`PostProcessor3D`'s
#: `FieldsCalculator`), so a bundle that imports cleanly and did not collect
#: it still fails on the first result. Checked as a file, not an import.
_PYAEDT_DATA_FILES: tuple[tuple[str, str], ...] = (
    (
        "ansys.aedt.core",
        "visualization/post/fields_calculator_files/expression_catalog.toml",
    ),
)


@dataclass(frozen=True, slots=True)
class SolverImportCheck:
    module: str
    imported: bool
    detail: str
    optional: bool


def _check_module(name: str, optional: bool) -> SolverImportCheck:
    try:
        module = importlib.import_module(name)
    except Exception as error:  # noqa: BLE001 - any import failure is the answer
        return SolverImportCheck(name, False, f"{type(error).__name__}: {error}", optional)
    return SolverImportCheck(name, True, str(getattr(module, "__file__", "no __file__")), optional)


def _check_data_file(package: str, relative: str) -> SolverImportCheck:
    label = f"{package}:{relative.rsplit('/', 1)[-1]}"
    try:
        module = importlib.import_module(package)
        root = getattr(module, "__file__", None)
        if root is None:
            return SolverImportCheck(label, False, f"{package} has no __file__", False)
        from pathlib import Path

        path = Path(root).parent.joinpath(*relative.split("/"))
    except Exception as error:  # noqa: BLE001 - any failure is the answer
        return SolverImportCheck(label, False, f"{type(error).__name__}: {error}", False)
    if not path.is_file():
        return SolverImportCheck(label, False, f"missing: {path}", False)
    return SolverImportCheck(label, True, str(path), False)


def check_solver_imports() -> tuple[SolverImportCheck, ...]:
    """Import every solver module this build needs, and locate its data files."""
    return (
        *(_check_module(name, optional) for name, optional in _MODULES),
        *(_check_data_file(package, relative) for package, relative in _PYAEDT_DATA_FILES),
    )


def format_solver_import_report(
    checks: tuple[SolverImportCheck, ...],
) -> tuple[str, bool]:
    """The report to print, and whether the build passed.

    An optional module's absence is reported and does not fail the check --
    FEMM not being installed is a normal configuration, not a broken build.
    """
    lines: list[str] = []
    ok = True
    for check in checks:
        if check.imported:
            status = "ok"
        elif check.optional:
            status = "absent (optional)"
        else:
            status = "FAILED"
            ok = False
        lines.append(f"{status:>18}  {check.module}  {check.detail}")
    lines.append(
        "This checks imports and data files only. A solve needs AEDT 2025 R2 "
        "Commercial on this machine and is not exercised here."
    )
    return "\n".join(lines), ok
