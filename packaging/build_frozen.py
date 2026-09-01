"""Freeze the application into a one-folder PyInstaller bundle.

The catalog index is generated here, never copied: `artifacts/` is
git-ignored, so `artifacts/catalog/catalog.sqlite` exists only where someone
has already run `tools.build_catalog`. Shipping an installer that silently
skipped that step would put an application in front of a user that starts
and shows an empty core list -- the worst outcome available here, because it
looks like it worked. So this script builds the index into a temporary
directory, checks it actually has cores in it, and only then hands
PyInstaller the result -- via an environment variable the spec file reads at
Analysis time, since a `.spec` file takes no command-line arguments of its
own.

Not a Python package: this directory has no `__init__.py` on purpose. The
`packaging` name already belongs to a direct dependency of this project (see
`packaging>=24.2,<27` in pyproject.toml); making this directory importable
as `packaging.build_frozen` would risk shadowing that dependency for
anything else that imports `packaging` while the repo root is on
`sys.path`. Run this file directly, or load it by path (see
`tests/unit/tools/test_build_frozen.py`).

Usage: .venv/Scripts/python.exe packaging/build_frozen.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = Path(__file__).with_name("inductor-designer.spec")

#: Read by `inductor-designer.spec` at Analysis time -- this is how the
#: generated catalog's path crosses from this script into the frozen
#: bundle's `datas`, since the spec file itself takes no arguments.
CATALOG_ENV_VAR = "INDUCTOR_DESIGNER_BUILD_CATALOG"


class CatalogBuildError(RuntimeError):
    """The generated catalog has no usable index -- see module docstring."""


def build_catalog(source_root: Path, schema_root: Path, out_dir: Path) -> Path:
    """Compile canonical catalog YAML into a SQLite index under `out_dir`.

    Raises `CatalogBuildError` rather than letting a missing or empty index
    reach PyInstaller silently -- a fresh clone that never ran
    `tools.build_catalog` has an empty `source_root` and must fail here, not
    ship a bundle whose application starts with no cores at all.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from tools.build_catalog import build

    out_path = out_dir / "catalog.sqlite"
    build(source_root, schema_root, out_path)
    if not out_path.is_file():
        raise CatalogBuildError(f"tools.build_catalog produced no file at {out_path}")
    # `sqlite3.Connection`'s context manager only wraps the transaction, not
    # the file handle -- an unclosed connection keeps the file locked on
    # Windows, which then fails the temporary directory's own cleanup.
    connection = sqlite3.connect(out_path)
    try:
        core_count = connection.execute("SELECT COUNT(*) FROM cores").fetchone()[0]
    finally:
        connection.close()
    if core_count == 0:
        raise CatalogBuildError(
            f"Generated catalog at {out_path} has zero cores; refusing to feed "
            "PyInstaller a bundle whose application would start with an empty "
            "core list."
        )
    return out_path


def resolve_datas(repo_root: Path, catalog_path: Path) -> list[tuple[str, str]]:
    """The `(source, dest)` pairs PyInstaller's `datas` needs.

    The first four mirror exactly what `adapters/system/resources.py`
    resolves at runtime for a frozen build -- `resource_root()` returns
    `sys._MEIPASS` directly there, so each destination here must equal the
    relative path that module joins onto it, or the bundle finds no data.
    The QML directory is not one of those four resources -- it is Python
    package data `ui/main.py`'s `qml_directory()` locates next to the
    frozen `ui/main.py` -- but without it the bundle starts and shows a
    blank window.
    """
    return [
        (str(repo_root / "schemas"), "schemas"),
        (str(repo_root / "compatibility"), "compatibility"),
        (str(repo_root / "materials-overlay"), "materials-overlay"),
        (str(catalog_path), "artifacts/catalog"),
        (
            str(repo_root / "src" / "inductor_designer" / "ui" / "qml"),
            "inductor_designer/ui/qml",
        ),
    ]


def _pyinstaller_run(args: list[str]) -> None:  # pragma: no cover - thin wrapper, mocked in tests
    from PyInstaller.__main__ import run

    run(args)


def main(argv: list[str] | None = None) -> int:
    with tempfile.TemporaryDirectory(prefix="inductor-designer-catalog-") as tmp:
        try:
            catalog_path = build_catalog(
                REPO_ROOT / "catalog", REPO_ROOT / "schemas" / "catalog", Path(tmp)
            )
        except CatalogBuildError as error:
            raise SystemExit(f"build_frozen: {error}") from error

        os.environ[CATALOG_ENV_VAR] = str(catalog_path)
        _pyinstaller_run([str(SPEC_PATH), "--noconfirm", *(argv or [])])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
