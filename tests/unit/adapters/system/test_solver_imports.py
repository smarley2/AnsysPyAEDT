"""Can the solver stack be imported, and are its data files really there?

Known risk 2 of the M10 release record: PyAEDT has only ever been exercised
from source, and a frozen Qt/PyAEDT bundle fails in exactly two ways that no
source run can reveal -- a lazily imported module that PyInstaller never saw,
and a data file the library reads off disk that was never collected. Both are
import-time facts, so both can be checked without an AEDT session, a license,
or a solve.

What this cannot check is a solve. That still needs AEDT, and it stays with
whoever has one.
"""

from __future__ import annotations

import pytest

from inductor_designer.adapters.system.solver_imports import (
    SolverImportCheck,
    check_solver_imports,
    format_solver_import_report,
)
from tests.optional_extras import needs_pyaedt


def test_every_module_the_solver_adapters_import_is_checked() -> None:
    """The list is the point: a module missing from it is a module whose
    absence the frozen bundle discovers in front of a user, mid-run."""
    names = {check.module for check in check_solver_imports()}
    assert "ansys.aedt.core" in names
    assert "ansys.aedt.core.modules.boundary.maxwell_boundary" in names
    assert "femm" in names


@needs_pyaedt
def test_a_module_that_imports_reports_ok_with_its_file() -> None:
    checks = {check.module: check for check in check_solver_imports()}
    # `json` stands in for nothing here -- this asserts on a real solver
    # module, and PyAEDT is a hard dependency of this project.
    pyaedt = checks["ansys.aedt.core"]
    assert pyaedt.imported is True, pyaedt.detail
    assert pyaedt.detail


@needs_pyaedt
def test_the_pyaedt_data_file_is_reported_by_path_and_existence() -> None:
    """The expression catalog PyAEDT reads on every result read. In a bundle
    that did not collect it, importing succeeds and reading a result fails --
    which is why existence is checked, not just the import."""
    checks = {check.module: check for check in check_solver_imports()}
    catalog = checks["ansys.aedt.core:expression_catalog.toml"]
    assert catalog.imported is True, catalog.detail
    assert "expression_catalog.toml" in catalog.detail


def test_an_optional_module_that_is_absent_is_reported_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FEMM is optional by design (the release notes say so), so its absence
    is a line in the report, not a failure of the check."""
    import importlib

    real_import = importlib.import_module

    def fake_import(name: str) -> object:
        if name == "femm":
            raise ModuleNotFoundError("No module named 'femm'")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    checks = {check.module: check for check in check_solver_imports()}
    assert checks["femm"].imported is False
    assert checks["femm"].optional is True
    assert "femm" in checks["femm"].detail


def test_the_report_names_every_failure_and_says_whether_it_is_fatal() -> None:
    report, ok = format_solver_import_report(
        (
            SolverImportCheck("ansys.aedt.core", True, "…/core/__init__.py", False),
            SolverImportCheck("femm", False, "not installed", True),
        )
    )
    assert ok is True  # an optional module's absence is not a failure
    assert "ansys.aedt.core" in report
    assert "femm" in report

    report, ok = format_solver_import_report(
        (SolverImportCheck("ansys.aedt.core", False, "boom", False),)
    )
    assert ok is False
    assert "boom" in report
