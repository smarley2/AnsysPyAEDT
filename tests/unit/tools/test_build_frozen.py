"""Tests for `packaging/build_frozen.py`'s own logic -- not the freeze itself.

No PyInstaller build runs here: that is slow and belongs to a manual or CI
packaging step, not the unit suite. What must never regress silently is
covered instead -- refusing to hand PyInstaller a catalog with zero cores,
and making sure the catalog `main()` actually generated (not some other
path) is what reaches PyInstaller.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_build_frozen() -> ModuleType:
    """Load `packaging/build_frozen.py` by path, not by package import.

    `packaging` is also the name of a direct PyPI dependency of this project
    (see pyproject.toml's `packaging>=24.2,<27`). This repository's
    `packaging/` directory is deliberately a plain directory, not a Python
    package -- `import packaging.build_frozen` would risk shadowing that
    dependency for anything else importing `packaging` while the repo root
    is on `sys.path`, which it is under pytest. Loading by file path never
    touches the `packaging` name at all.
    """
    spec = importlib.util.spec_from_file_location(
        "inductor_designer_build_frozen",
        REPO_ROOT / "packaging" / "build_frozen.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_frozen = _load_build_frozen()


def test_build_catalog_refuses_an_index_with_no_cores(tmp_path: Path) -> None:
    """An empty source tree must not produce a catalog PyInstaller would ship."""
    empty_source = tmp_path / "empty-catalog"
    empty_source.mkdir()
    with pytest.raises(build_frozen.CatalogBuildError, match="zero cores"):
        build_frozen.build_catalog(
            empty_source, REPO_ROOT / "schemas" / "catalog", tmp_path / "out"
        )


def test_build_catalog_builds_the_real_catalog(tmp_path: Path) -> None:
    out_path = build_frozen.build_catalog(
        REPO_ROOT / "catalog", REPO_ROOT / "schemas" / "catalog", tmp_path / "out"
    )
    assert out_path.is_file()
    connection = sqlite3.connect(out_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM cores").fetchone()[0] > 0
    finally:
        connection.close()


def test_resolve_datas_matches_the_resource_seam_layout() -> None:
    """Every destination here must be exactly what `resources.py` joins onto
    `resource_root()` for a frozen build (`sys._MEIPASS` itself) -- a mismatch
    here is a bundle that finds no data."""
    catalog_path = REPO_ROOT / "does-not-exist" / "catalog.sqlite"
    mapping = dict(build_frozen.resolve_datas(REPO_ROOT, catalog_path))
    assert mapping[str(REPO_ROOT / "schemas")] == "schemas"
    assert mapping[str(REPO_ROOT / "compatibility")] == "compatibility"
    assert mapping[str(REPO_ROOT / "materials-overlay")] == "materials-overlay"
    assert mapping[str(catalog_path)] == "artifacts/catalog"
    assert (
        mapping[str(REPO_ROOT / "src" / "inductor_designer" / "ui" / "qml")]
        == "inductor_designer/ui/qml"
    )


def test_main_refuses_when_the_catalog_build_produces_no_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` must not reach PyInstaller at all when the catalog build fails."""
    calls: list[list[str]] = []
    monkeypatch.setattr(build_frozen, "_pyinstaller_run", lambda args: calls.append(args))
    # No `catalog/` directory under this fake repo root -- `build()` globs
    # nothing and produces zero cores, exactly like a fresh clone that never
    # ran `tools.build_catalog`.
    monkeypatch.setattr(build_frozen, "REPO_ROOT", tmp_path)
    schema_dir = tmp_path / "schemas" / "catalog"
    schema_dir.mkdir(parents=True)
    for name in ("core.v1.schema.json", "conductor.v1.schema.json"):
        (schema_dir / name).write_text(
            (REPO_ROOT / "schemas" / "catalog" / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    with pytest.raises(SystemExit, match="zero cores"):
        build_frozen.main([])
    assert calls == []


def test_main_passes_the_generated_catalog_path_to_pyinstaller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog `build_catalog` produced -- not a hand-picked path -- is
    what must reach PyInstaller, and it must still exist (and be populated)
    at the moment PyInstaller is invoked."""
    captured: dict[str, object] = {}

    def fake_pyinstaller_run(args: list[str]) -> None:
        catalog_path = Path(os.environ[build_frozen.CATALOG_ENV_VAR])
        # Closed explicitly -- an open sqlite3 connection keeps the file
        # locked on Windows and `main()`'s temp-dir cleanup would fail.
        connection = sqlite3.connect(catalog_path)
        try:
            core_count = connection.execute("SELECT COUNT(*) FROM cores").fetchone()[0]
        finally:
            connection.close()
        captured["args"] = args
        captured["core_count"] = core_count

    monkeypatch.setattr(build_frozen, "_pyinstaller_run", fake_pyinstaller_run)

    build_frozen.main([])

    assert captured["args"] == [str(build_frozen.SPEC_PATH), "--noconfirm"]
    assert captured["core_count"] > 0
