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

Usage: .venv/Scripts/python.exe packaging/build_frozen.py [--installer]

`--installer` additionally compiles `packaging/installer.iss` with Inno
Setup's `ISCC.exe` once the bundle is built (M10 Task 4). It is optional and
off by default: Inno Setup is a separate install this script never performs
for you (see `find_iscc` below), so a machine without it can still produce
the frozen bundle on its own.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = Path(__file__).with_name("inductor-designer.spec")
ISS_PATH = Path(__file__).with_name("installer.iss")

#: Read by `inductor-designer.spec` at Analysis time -- this is how the
#: generated catalog's path crosses from this script into the frozen
#: bundle's `datas`, since the spec file itself takes no arguments.
CATALOG_ENV_VAR = "INDUCTOR_DESIGNER_BUILD_CATALOG"

#: Where Inno Setup 6's command-line compiler installs by default. Checked
#: in order; `%ProgramFiles(x86)%` is where Inno Setup's own installer puts
#: it on 64-bit Windows regardless of this script's own architecture.
_ISCC_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Inno Setup 6"
    / "ISCC.exe",
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
)

#: Override for a non-default Inno Setup install -- checked before the
#: standard locations above.
_ISCC_OVERRIDE_ENV_VAR = "INDUCTOR_DESIGNER_ISCC"


class CatalogBuildError(RuntimeError):
    """The generated catalog has no usable index -- see module docstring."""


class InnoSetupNotFoundError(RuntimeError):
    """`ISCC.exe` was not found -- `--installer` needs Inno Setup 6 installed.

    This script never installs Inno Setup itself: that is a machine-wide
    change outside a packaging build's authority. It only looks for a
    compiler that is already there.
    """


def build_catalog(source_root: Path, schema_root: Path, out_dir: Path) -> Path:
    """Compile canonical catalog YAML into a SQLite index under `out_dir`.

    Raises `CatalogBuildError` rather than letting a missing or empty index
    reach PyInstaller silently -- a fresh clone that never ran
    `tools.build_catalog` has an empty `source_root` and must fail here, not
    ship a bundle whose application starts with no cores at all.
    """
    # Guarded, not unconditional -- an unconditional insert on every call
    # would grow `sys.path` by one repo-root entry per invocation and never
    # pop it, leaving `packaging/`'s shadowing risk (see module docstring)
    # on `sys.path` for the rest of the process.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from tools.build_catalog import build

    out_path = out_dir / "catalog.sqlite"
    build(source_root, schema_root, out_path)
    if not out_path.is_file():
        raise CatalogBuildError(f"tools.build_catalog produced no file at {out_path}")
    # `sqlite3.Connection`'s context manager only wraps the transaction, not
    # the file handle -- an unclosed connection keeps the file locked on
    # Windows, which then fails the temporary directory's own cleanup.
    try:
        connection = sqlite3.connect(out_path)
        try:
            core_count = connection.execute("SELECT COUNT(*) FROM cores").fetchone()[0]
        finally:
            connection.close()
    except sqlite3.Error as error:
        # A truncated or zero-byte catalog (e.g. a build interrupted
        # mid-write) must still surface as `CatalogBuildError`, not a raw
        # `sqlite3.DatabaseError`/`OperationalError` -- PyInstaller must
        # never be reached either way, but the message should name the
        # actual cause.
        raise CatalogBuildError(
            f"Generated catalog at {out_path} is not a valid SQLite database: {error}"
        ) from error
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


def find_iscc() -> Path:
    """Locate Inno Setup 6's command-line compiler.

    Raises `InnoSetupNotFoundError` naming the download page rather than
    installing anything -- Inno Setup is a machine-wide change this build
    step is not authorised to make silently.
    """
    override = os.environ.get(_ISCC_OVERRIDE_ENV_VAR)
    if override:
        candidate = Path(override)
        if candidate.is_file():
            return candidate
        raise InnoSetupNotFoundError(
            f"{_ISCC_OVERRIDE_ENV_VAR}={override!r} does not point to a file."
        )
    for candidate in _ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    searched = ", ".join(str(candidate) for candidate in _ISCC_CANDIDATES)
    raise InnoSetupNotFoundError(
        "ISCC.exe (Inno Setup 6's command-line compiler) was not found. Looked "
        f"in: {searched}. Install Inno Setup 6 from "
        "https://jrsoftware.org/isdl.php, or set "
        f"{_ISCC_OVERRIDE_ENV_VAR} to an existing ISCC.exe path. This build "
        "step never installs it for you."
    )


def compile_installer(
    iscc_path: Path, version: str
) -> None:  # pragma: no cover - thin wrapper, mocked in tests
    """Compile `installer.iss` with Inno Setup, passing the app version through.

    `__about__.py` stays the single source of truth: the version crosses into
    the `.iss` as a preprocessor define (`/DMyAppVersion=...`) rather than
    being duplicated as a literal in the script, the same reasoning
    `resolve_datas` above applies to the bundle's data paths.
    """
    subprocess.run(
        [str(iscc_path), f"/DMyAppVersion={version}", str(ISS_PATH)],
        check=True,
        cwd=REPO_ROOT,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--installer",
        action="store_true",
        help="Also compile packaging/installer.iss with Inno Setup after the bundle builds.",
    )
    args, pyinstaller_args = parser.parse_known_args(argv or [])

    with tempfile.TemporaryDirectory(prefix="inductor-designer-catalog-") as tmp:
        try:
            catalog_path = build_catalog(
                REPO_ROOT / "catalog", REPO_ROOT / "schemas" / "catalog", Path(tmp)
            )
        except CatalogBuildError as error:
            raise SystemExit(f"build_frozen: {error}") from error

        os.environ[CATALOG_ENV_VAR] = str(catalog_path)
        _pyinstaller_run([str(SPEC_PATH), "--noconfirm", *pyinstaller_args])

    if args.installer:
        try:
            iscc_path = find_iscc()
        except InnoSetupNotFoundError as error:
            raise SystemExit(f"build_frozen: {error}") from error
        from inductor_designer.__about__ import __version__

        compile_installer(iscc_path, __version__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
