from pathlib import Path

import pytest

from tools.check_architecture import Violation, find_forbidden_imports


@pytest.mark.parametrize(
    ("statement", "imported"),
    [
        ("from ansys.aedt.core import Maxwell3d\n", "ansys.aedt.core"),
        ("import pyaedt\n", "pyaedt"),
        ("from PySide6 import QtCore\n", "PySide6"),
        ("import sqlite3\n", "sqlite3"),
        ("import os\n", "os"),
        ("import platform\n", "platform"),
        ("from pathlib import Path\n", "pathlib"),
        ("import subprocess\n", "subprocess"),
        ("import shutil\n", "shutil"),
        ("import tempfile\n", "tempfile"),
        ("import socket\n", "socket"),
        ("import ctypes\n", "ctypes"),
        ("import multiprocessing\n", "multiprocessing"),
        ("import resource\n", "resource"),
        ("import winreg\n", "winreg"),
    ],
)
def test_finds_forbidden_dependency_in_inner_package(
    tmp_path: Path,
    statement: str,
    imported: str,
) -> None:
    source = tmp_path / "inductor_designer" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text(statement, encoding="utf-8")

    assert find_forbidden_imports(tmp_path) == (
        Violation(source, 1, imported, "domain"),
    )


def test_application_rejects_infrastructure_but_allows_pathlib(tmp_path: Path) -> None:
    source = tmp_path / "inductor_designer" / "application" / "ports" / "gateway.py"
    source.parent.mkdir(parents=True)
    source.write_text("from pathlib import Path\nimport sqlite3\n", encoding="utf-8")

    assert find_forbidden_imports(tmp_path) == (
        Violation(source, 2, "sqlite3", "application"),
    )


def test_repository_inner_packages_respect_boundaries() -> None:
    assert find_forbidden_imports(Path("src")) == ()
