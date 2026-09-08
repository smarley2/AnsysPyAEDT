"""The resource seam this task exists for: one place that answers "where is
my data", identical in a source checkout, an installed wheel, and a
PyInstaller bundle -- see `.superpowers/sdd/m10-task-1-brief.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from inductor_designer.adapters.system import resources


def _write_resource_tree(root: Path) -> None:
    """A minimal but complete four-resource layout under ``root``."""
    (root / "schemas").mkdir(parents=True)
    (root / "schemas" / "marker.json").write_text("{}", encoding="utf-8")
    (root / "artifacts" / "catalog").mkdir(parents=True)
    (root / "artifacts" / "catalog" / "catalog.sqlite").write_bytes(b"")
    (root / "compatibility").mkdir(parents=True)
    (root / "compatibility" / "aedt-matrix.yml").write_text("matrix: []", encoding="utf-8")
    (root / "materials-overlay").mkdir(parents=True)


def test_a_source_checkout_resolves_every_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment every developer and every test runs in. No variable is
    set, the working directory is arbitrary, and all four must still resolve
    to files that exist."""
    monkeypatch.delenv(resources.OVERRIDE_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert resources.schemas_directory().is_dir()
    assert resources.catalog_index_path().is_file()
    assert resources.compatibility_matrix_path().is_file()
    assert resources.material_overlay_directory().is_dir()
    assert resources.missing_resources() == ()


def test_a_frozen_bundle_reads_beside_the_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`sys.frozen` and `sys._MEIPASS` are what PyInstaller sets; the product
    only ever runs in this mode, and no test would otherwise exercise it."""
    bundle_directory = tmp_path / "bundle"
    _write_resource_tree(bundle_directory)
    monkeypatch.delenv(resources.OVERRIDE_VARIABLE, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_directory), raising=False)

    assert resources.resource_root() == bundle_directory
    assert resources.schemas_directory().is_dir()
    assert resources.catalog_index_path().is_file()
    assert resources.compatibility_matrix_path().is_file()
    assert resources.material_overlay_directory().is_dir()


def test_an_override_wins_over_every_other_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A support engineer must be able to point a shipped build at a
    corrected catalog without waiting for a rebuild."""
    override_root = tmp_path / "override"
    _write_resource_tree(override_root)
    # Even a frozen bundle claiming a different root must lose to the
    # override -- it is checked first, ahead of every other source.
    decoy_bundle = tmp_path / "decoy-bundle"
    _write_resource_tree(decoy_bundle)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(decoy_bundle), raising=False)
    monkeypatch.setenv(resources.OVERRIDE_VARIABLE, str(override_root))

    assert resources.resource_root() == override_root
    assert resources.catalog_index_path() == override_root / "artifacts" / "catalog" / (
        "catalog.sqlite"
    )
    assert resources.missing_resources() == ()


def test_missing_resources_are_reported_together_and_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One launch, one list. Reporting the first absence only means a user
    with three missing files learns that across three launches."""
    incomplete_root = tmp_path / "incomplete"
    incomplete_root.mkdir()
    (incomplete_root / "schemas").mkdir()
    (incomplete_root / "schemas" / "marker.json").write_text("{}", encoding="utf-8")
    # catalog index, compatibility matrix and material overlay are all left
    # absent.
    monkeypatch.setenv(resources.OVERRIDE_VARIABLE, str(incomplete_root))

    missing = resources.missing_resources()

    names = {item.name for item in missing}
    assert names == {"catalog index", "compatibility matrix", "material overlay directory"}
    assert len(missing) == 3
    for item in missing:
        assert not item.path.exists()


def test_an_installed_wheel_resolves_from_the_packaged_resources_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`pip install` depends on this branch (`resources.py`'s ``packaged``
    check), proven before this test only by a manual wheel extraction --
    nothing in the suite exercised it. `_PACKAGE_DIRECTORY` is hoisted at
    module level exactly so a test can point it at a `tmp_path` tree without
    faking `__file__` or building a real wheel."""
    package_directory = tmp_path / "site-packages" / "inductor_designer"
    package_directory.mkdir(parents=True)
    packaged_resources = package_directory / "_resources"
    _write_resource_tree(packaged_resources)
    monkeypatch.delenv(resources.OVERRIDE_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(resources, "_PACKAGE_DIRECTORY", package_directory)

    assert resources.resource_root() == packaged_resources
    assert resources.schemas_directory().is_dir()
    assert resources.catalog_index_path().is_file()
    assert resources.compatibility_matrix_path().is_file()
    assert resources.material_overlay_directory().is_dir()
    assert resources.missing_resources() == ()


def _make_checkout_root_markers(root: Path) -> None:
    """The two directories `_find_source_checkout_root` looks for: the
    top-level `schemas/` and `catalog/` that mark this project's root --
    distinct from `_write_resource_tree`'s `artifacts/catalog/`, which is
    build *output*, not the source-checkout marker."""
    (root / "schemas").mkdir(parents=True, exist_ok=True)
    (root / "catalog").mkdir(parents=True, exist_ok=True)


def test_a_decoy_ancestor_is_not_mistaken_for_the_checkout_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Reviewer's exact repro: the checkout root has neither `schemas/` nor
    `catalog/`, but `outer/`, two levels up, happens to hold both --
    reproducing a decoy directory that is not this project. Before the
    `pyproject.toml` marker was added to the predicate, the walk-up stopped
    at `outer` and reported nothing missing: silently wrong data. It must
    not resolve there now."""
    outer = tmp_path / "outer"
    _make_checkout_root_markers(outer)
    nested_checkout = outer / "checkout"
    package_directory = nested_checkout / "src" / "inductor_designer"
    package_directory.mkdir(parents=True)
    monkeypatch.delenv(resources.OVERRIDE_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(resources, "_PACKAGE_DIRECTORY", package_directory)

    assert resources.resource_root() != outer
    # The pre-fix defect was not just resolving to the wrong place, but
    # reporting nothing missing while doing it.
    assert resources.missing_resources() != ()


def test_a_real_checkout_root_still_resolves_beside_a_decoy_ancestor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The positive case for the same predicate: a nested checkout that
    genuinely has `schemas/`, `catalog/` *and* `pyproject.toml` must still
    win, even with a decoy ancestor (`outer/`, itself data-shaped but not a
    real checkout) further up the same walk."""
    outer = tmp_path / "outer"
    _make_checkout_root_markers(outer)
    nested_checkout = outer / "checkout"
    _write_resource_tree(nested_checkout)
    _make_checkout_root_markers(nested_checkout)
    (nested_checkout / "pyproject.toml").write_text("", encoding="utf-8")
    package_directory = nested_checkout / "src" / "inductor_designer"
    package_directory.mkdir(parents=True)
    monkeypatch.delenv(resources.OVERRIDE_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(resources, "_PACKAGE_DIRECTORY", package_directory)

    assert resources.resource_root() == nested_checkout
    assert resources.missing_resources() == ()


def test_the_working_directory_does_not_matter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The defect this task exists for: every path was relative to the
    working directory, so a shortcut launch resolved none of them."""
    monkeypatch.delenv(resources.OVERRIDE_VARIABLE, raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    unrelated_directory = tmp_path / "wherever-a-shortcut-happens-to-start"
    unrelated_directory.mkdir()
    monkeypatch.chdir(unrelated_directory)

    assert resources.missing_resources() == ()
