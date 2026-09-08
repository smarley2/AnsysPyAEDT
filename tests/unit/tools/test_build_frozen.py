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
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.optional_extras import needs_pyaedt, needs_pyinstaller

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


def test_build_catalog_does_not_grow_sys_path_on_repeated_calls(tmp_path: Path) -> None:
    """`sys.path.insert(0, str(REPO_ROOT))` must be guarded, not
    unconditional -- an unconditional insert on every call grows `sys.path`
    by one repo-root entry per invocation and never pops it, leaving
    `packaging/`'s name-shadowing risk (see module docstring) on `sys.path`
    for the rest of the process."""
    before = sys.path.count(str(build_frozen.REPO_ROOT))
    for i in range(3):
        build_frozen.build_catalog(
            REPO_ROOT / "catalog", REPO_ROOT / "schemas" / "catalog", tmp_path / f"out-{i}"
        )
    after = sys.path.count(str(build_frozen.REPO_ROOT))
    assert after == before


def test_build_catalog_wraps_a_corrupt_sqlite_file_as_catalog_build_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated or zero-byte catalog (e.g. a build interrupted mid-write)
    must surface as `CatalogBuildError` naming the cause -- not a raw
    `sqlite3.DatabaseError`/`OperationalError` escaping past it. PyInstaller
    is never reached either way, but the message should say why."""
    import tools.build_catalog as build_catalog_module

    def _write_garbage(source_root: Path, schema_root: Path, out_path: Path) -> None:
        out_path.write_bytes(b"not a sqlite database")

    monkeypatch.setattr(build_catalog_module, "build", _write_garbage)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    with pytest.raises(build_frozen.CatalogBuildError, match="not a valid SQLite database"):
        build_frozen.build_catalog(
            REPO_ROOT / "catalog", REPO_ROOT / "schemas" / "catalog", out_dir
        )


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


@needs_pyaedt
@needs_pyinstaller
def test_spec_bundles_pyaedt_data_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Executes `inductor-designer.spec`'s `datas=` build the same way
    PyInstaller does -- `Analysis`/`PYZ`/`EXE`/`COLLECT` stubbed out so no
    real bundling happens -- and asserts pyaedt's data files (from
    `collect_data_files("ansys.aedt.core")`) reach `Analysis`.

    Without them the frozen bundle ships zero of pyaedt's 114 non-Python
    data files, including `visualization/post/fields_calculator_files/
    expression_catalog.toml`. `PostProcessor3D.__init__` reads that file
    eagerly through `FieldsCalculator` (`fields_calculator.py`), and every
    result path in this application goes through `.post`
    (`adapters/pyaedt/live_app.py`, `maxwell3d.py`, `maxwell2d.py`) -- so a
    bundle missing it can generate a solve but never read one back.
    """
    captured: dict[str, object] = {}

    class _FakeAnalysis:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["datas"] = kwargs.get("datas")
            self.pure: list[object] = []
            self.scripts: list[object] = []
            self.binaries: list[object] = []
            self.zipfiles: list[object] = []
            self.datas = kwargs.get("datas", [])

    monkeypatch.setenv(
        build_frozen.CATALOG_ENV_VAR, str(REPO_ROOT / "does-not-exist" / "catalog.sqlite")
    )
    spec_path = REPO_ROOT / "packaging" / "inductor-designer.spec"
    namespace: dict[str, object] = {
        "SPECPATH": str(REPO_ROOT / "packaging"),
        "Analysis": _FakeAnalysis,
        "PYZ": lambda *args, **kwargs: None,
        "EXE": lambda *args, **kwargs: None,
        "COLLECT": lambda *args, **kwargs: None,
    }
    exec(compile(spec_path.read_text(encoding="utf-8"), str(spec_path), "exec"), namespace)

    datas = captured["datas"]
    assert datas is not None
    assert any(
        Path(str(source)).name == "expression_catalog.toml" for source, _dest in datas  # type: ignore[misc]
    ), "spec's datas= must include pyaedt's data files (collect_data_files('ansys.aedt.core'))"


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


def test_find_iscc_raises_when_not_found_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No override set, and neither standard Inno Setup location exists --
    `find_iscc` must name the download page rather than installing anything
    itself (M10 Task 4: Inno Setup is a machine-wide change this build step
    is not authorised to make silently)."""
    monkeypatch.delenv(build_frozen._ISCC_OVERRIDE_ENV_VAR, raising=False)
    monkeypatch.setattr(
        build_frozen,
        "_ISCC_CANDIDATES",
        (tmp_path / "nowhere" / "ISCC.exe",),
    )
    with pytest.raises(build_frozen.InnoSetupNotFoundError, match="jrsoftware.org"):
        build_frozen.find_iscc()


def test_find_iscc_uses_a_standard_candidate_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    iscc = tmp_path / "Inno Setup 6" / "ISCC.exe"
    iscc.parent.mkdir(parents=True)
    iscc.write_text("stub")
    monkeypatch.delenv(build_frozen._ISCC_OVERRIDE_ENV_VAR, raising=False)
    monkeypatch.setattr(build_frozen, "_ISCC_CANDIDATES", (iscc,))
    assert build_frozen.find_iscc() == iscc


def test_iscc_candidates_include_the_per_user_install_location() -> None:
    """The only route open to a builder without administrator rights.

    Every other `find_iscc` test substitutes `_ISCC_CANDIDATES` wholesale,
    so without this one nothing asserts what the real tuple holds -- and
    dropping this entry does not fail any test while leaving a non-admin
    builder with a "not found" refusal and a working ISCC.exe installed
    under their own profile. That is exactly how the 0.1.0 installer was
    compiled.
    """
    parts = [candidate.parts for candidate in build_frozen._ISCC_CANDIDATES]
    assert any(
        "Programs" in candidate and candidate[-2] == "Inno Setup 6" for candidate in parts
    ), f"no %LOCALAPPDATA%\\Programs candidate in {build_frozen._ISCC_CANDIDATES}"


def test_find_iscc_prefers_the_override_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    override = tmp_path / "custom" / "ISCC.exe"
    override.parent.mkdir(parents=True)
    override.write_text("stub")
    monkeypatch.setenv(build_frozen._ISCC_OVERRIDE_ENV_VAR, str(override))
    # A candidate that also exists must lose to the override.
    monkeypatch.setattr(build_frozen, "_ISCC_CANDIDATES", (tmp_path / "other" / "ISCC.exe",))
    assert build_frozen.find_iscc() == override


def test_find_iscc_rejects_an_override_that_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(build_frozen._ISCC_OVERRIDE_ENV_VAR, str(tmp_path / "missing.exe"))
    with pytest.raises(build_frozen.InnoSetupNotFoundError, match="does not point to a file"):
        build_frozen.find_iscc()


def test_main_without_installer_flag_never_looks_for_iscc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default build must not require Inno Setup at all -- a machine
    with only PyInstaller installed must still be able to freeze the
    bundle."""
    monkeypatch.setattr(build_frozen, "_pyinstaller_run", lambda args: None)
    monkeypatch.setattr(build_frozen, "emit_checksums", lambda version, **kwargs: None)

    def _fail_if_called() -> Path:
        raise AssertionError("find_iscc must not be called without --installer")

    monkeypatch.setattr(build_frozen, "find_iscc", _fail_if_called)

    assert build_frozen.main([]) == 0


def test_main_with_installer_flag_refuses_clearly_when_iscc_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_frozen, "_pyinstaller_run", lambda args: None)

    def _raise_not_found() -> Path:
        raise build_frozen.InnoSetupNotFoundError("ISCC.exe was not found. See jrsoftware.org.")

    monkeypatch.setattr(build_frozen, "find_iscc", _raise_not_found)
    calls: list[tuple[Path, str]] = []

    def _record(iscc_path: object, version: object) -> None:
        calls.append((iscc_path, version))

    monkeypatch.setattr(build_frozen, "compile_installer", _record)

    with pytest.raises(SystemExit, match="jrsoftware.org"):
        build_frozen.main(["--installer"])
    assert calls == []


def test_main_with_installer_flag_compiles_using_the_about_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_frozen, "_pyinstaller_run", lambda args: None)
    fake_iscc = tmp_path / "ISCC.exe"
    monkeypatch.setattr(build_frozen, "find_iscc", lambda: fake_iscc)
    calls: list[tuple[Path, str]] = []

    def _record(iscc_path: object, version: object) -> None:
        calls.append((iscc_path, version))

    monkeypatch.setattr(build_frozen, "compile_installer", _record)
    checksum_calls: list[str] = []
    monkeypatch.setattr(
        build_frozen,
        "emit_checksums",
        lambda version, **kwargs: checksum_calls.append(version),
    )

    from inductor_designer.__about__ import __version__

    assert build_frozen.main(["--installer"]) == 0
    assert calls == [(fake_iscc, __version__)]
    assert checksum_calls == [__version__]


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
    monkeypatch.setattr(build_frozen, "emit_checksums", lambda version, **kwargs: None)

    build_frozen.main([])

    assert captured["args"] == [str(build_frozen.SPEC_PATH), "--noconfirm"]
    assert captured["core_count"] > 0


# --- Checksums (M10 Task 5): SHA256SUMS.txt for the bundle archive and the
# installer. Artifacts are named by hash and filename only, never a URL --
# the plan's migration note requires the release notes and this file to
# stay correct if the repository host ever moves off GitHub. ---


def test_sha256_file_matches_a_known_test_vector(tmp_path: Path) -> None:
    """Checked against a NIST-published SHA-256 test vector
    (SHA256("abc") = ba7816bf...), not against `hashlib` called a second
    time inside this test -- that would only prove the function agrees with
    itself, not that it computes SHA-256 at all."""
    sample = tmp_path / "sample.txt"
    sample.write_bytes(b"abc")
    assert (
        build_frozen.sha256_file(sample)
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_sha256_file_reads_large_files_in_chunks(tmp_path: Path) -> None:
    """A 300 MB bundle archive must never be loaded into memory whole to be
    hashed -- exercised here with a file larger than one read chunk."""
    big = tmp_path / "big.bin"
    payload = (b"x" * (1 << 20)) + b"y"  # bigger than a single 1 MiB chunk
    big.write_bytes(payload)
    import hashlib

    assert build_frozen.sha256_file(big) == hashlib.sha256(payload).hexdigest()


def test_write_checksums_uses_the_sha256sum_verifiable_format(tmp_path: Path) -> None:
    """Each line is `<64 lowercase hex chars><two spaces><filename>` -- the
    format `sha256sum -c` (and `Get-FileHash` by comparison) can verify
    directly, and only the basename appears, never a full path or a URL."""
    first = tmp_path / "artifacts" / "one.zip"
    first.parent.mkdir()
    first.write_bytes(b"hello")
    second = tmp_path / "elsewhere" / "two.exe"
    second.parent.mkdir()
    second.write_bytes(b"world")

    out_path = build_frozen.write_checksums([first, second], tmp_path / "SHA256SUMS.txt")

    lines = out_path.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824  one.zip",
        "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7  two.exe",
    ]
    assert "http" not in out_path.read_text(encoding="utf-8")
    assert str(tmp_path) not in out_path.read_text(encoding="utf-8")


def test_archive_bundle_zips_the_bundle_with_its_folder_as_the_top_level_entry(
    tmp_path: Path,
) -> None:
    """Unzipping must produce one `inductor-designer/` folder, not hundreds
    of loose files dumped into whatever directory the user picked."""
    import zipfile

    dist_dir = tmp_path / "dist"
    bundle_dir = dist_dir / "inductor-designer"
    (bundle_dir / "_internal").mkdir(parents=True)
    (bundle_dir / "inductor-designer.exe").write_bytes(b"stub-exe")
    (bundle_dir / "_internal" / "data.bin").write_bytes(b"stub-data")

    archive_path = build_frozen.archive_bundle(dist_dir, "0.1.0")

    assert archive_path == dist_dir / "inductor-designer-0.1.0-win64.zip"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "inductor-designer/inductor-designer.exe" in names
    assert "inductor-designer/_internal/data.bin" in names


def test_emit_checksums_covers_only_the_bundle_when_no_installer_was_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_frozen, "REPO_ROOT", tmp_path)
    bundle_dir = tmp_path / "dist" / "inductor-designer"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "inductor-designer.exe").write_bytes(b"stub-exe")

    out_path = build_frozen.emit_checksums("0.1.0", installer_built=False)

    assert out_path == tmp_path / "dist" / "SHA256SUMS.txt"
    content = out_path.read_text(encoding="utf-8")
    assert "inductor-designer-0.1.0-win64.zip" in content
    assert "setup.exe" not in content
    assert len(content.splitlines()) == 1


def test_emit_checksums_covers_the_installer_too_when_it_was_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_frozen, "REPO_ROOT", tmp_path)
    bundle_dir = tmp_path / "dist" / "inductor-designer"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "inductor-designer.exe").write_bytes(b"stub-exe")
    installer_dir = tmp_path / "dist" / "installer"
    installer_dir.mkdir(parents=True)
    (installer_dir / "inductor-designer-0.1.0-setup.exe").write_bytes(b"stub-installer")

    out_path = build_frozen.emit_checksums("0.1.0", installer_built=True)

    content = out_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert len(lines) == 2
    assert any(line.endswith("inductor-designer-0.1.0-win64.zip") for line in lines)
    assert any(line.endswith("inductor-designer-0.1.0-setup.exe") for line in lines)


def test_emit_checksums_ignores_an_installer_left_by_an_earlier_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`dist/installer/` is not cleaned between runs, so a bundle-only build
    that followed an `--installer` build would otherwise publish the old
    installer's hash beside a newly rebuilt bundle -- two entries in one
    checksums file that do not describe the same build. Someone verifying
    that hash would get a match and trust a stale installer."""
    monkeypatch.setattr(build_frozen, "REPO_ROOT", tmp_path)
    bundle_dir = tmp_path / "dist" / "inductor-designer"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "inductor-designer.exe").write_bytes(b"stub-exe")
    installer_dir = tmp_path / "dist" / "installer"
    installer_dir.mkdir(parents=True)
    (installer_dir / "inductor-designer-0.1.0-setup.exe").write_bytes(b"stale-installer")

    out_path = build_frozen.emit_checksums("0.1.0", installer_built=False)

    content = out_path.read_text(encoding="utf-8")
    assert "setup.exe" not in content
    assert len(content.splitlines()) == 1


def test_main_tells_emit_checksums_whether_it_compiled_an_installer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag must come from `--installer`, not from probing `dist/` --
    see `test_emit_checksums_ignores_an_installer_left_by_an_earlier_run`."""
    monkeypatch.setattr(build_frozen, "_pyinstaller_run", lambda args: None)
    monkeypatch.setattr(build_frozen, "find_iscc", lambda: Path("ISCC.exe"))
    monkeypatch.setattr(build_frozen, "compile_installer", lambda iscc, version: None)
    flags: list[bool] = []
    monkeypatch.setattr(
        build_frozen,
        "emit_checksums",
        lambda version, *, installer_built: flags.append(installer_built),
    )

    assert build_frozen.main([]) == 0
    assert build_frozen.main(["--installer"]) == 0
    assert flags == [False, True]


def test_main_calls_emit_checksums_with_the_apps_own_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wiring test: `main()` must pass its own package version, not a
    hand-picked or hard-coded one, matching the installer and the About
    box (same reasoning as `compile_installer`'s version argument)."""
    monkeypatch.setattr(build_frozen, "_pyinstaller_run", lambda args: None)
    calls: list[str] = []
    monkeypatch.setattr(
        build_frozen, "emit_checksums", lambda version, **kwargs: calls.append(version)
    )

    from inductor_designer.__about__ import __version__

    assert build_frozen.main([]) == 0
    assert calls == [__version__]
