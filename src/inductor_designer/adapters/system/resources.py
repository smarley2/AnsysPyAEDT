"""Where the shipped data lives, resolved for whichever environment is running.

Four resources ship with the application: the JSON schemas, the built
catalog index, the compatibility matrix, and the material overlay. Three
environments can be running this code -- a PyInstaller bundle launched from
a Start Menu shortcut (the product), an installed wheel (``pip install``),
and a source checkout (every developer, every test) -- and each keeps the
same relative layout under its own root, so this module needs exactly one
join per resource, never a per-environment branch past ``resource_root()``.

This module resolves and checks existence only. It never reads, parses or
validates a resource's content -- the repositories that already own each
format (``SchemaRepository``, ``SqliteCatalogRepository``, and so on) keep
owning it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NamedTuple

#: An explicit override, checked before every other source: a support
#: engineer can point a shipped build at a corrected catalog without a
#: rebuild. Will be documented in the release notes (M10 Task 5).
OVERRIDE_VARIABLE = "INDUCTOR_DESIGNER_RESOURCES"

# The relative layout shared, unchanged, by all three environments. A source
# checkout already has this shape at its root today (`artifacts/` holds
# build output rather than shipped source, but the catalog index inside it
# is still one of the four resources); the wheel and the frozen bundle
# mirror it under their own root so every accessor below is one join, with
# no environment-specific branch.
_SCHEMAS_RELATIVE = Path("schemas")
_CATALOG_INDEX_RELATIVE = Path("artifacts") / "catalog" / "catalog.sqlite"
_COMPATIBILITY_MATRIX_RELATIVE = Path("compatibility") / "aedt-matrix.yml"
_MATERIAL_OVERLAY_RELATIVE = Path("materials-overlay")

# Where the wheel's `force-include` table (see pyproject.toml) places the
# mirrored layout, relative to the installed package directory.
_PACKAGED_RESOURCES_DIRECTORY_NAME = "_resources"

# Hoisted to module level (rather than computed inline in `resource_root()`)
# so a test can monkeypatch it to a `tmp_path` tree and exercise the
# installed-wheel branch without faking `__file__` or building a real wheel.
_PACKAGE_DIRECTORY = Path(__file__).resolve().parents[2]


class MissingResource(NamedTuple):
    """One resource that did not resolve, named for a startup report."""

    name: str
    path: Path


def resource_root() -> Path:
    """The directory holding the four shipped resources, for this environment.

    Checked in this order; the first that answers wins:

    0. ``INDUCTOR_DESIGNER_RESOURCES``, an explicit override.
    1. Frozen (PyInstaller): the bundle directory, ``sys._MEIPASS``.
    2. Installed package: the ``_resources/`` directory shipped inside the
       wheel, next to ``inductor_designer/__init__.py``.
    3. Source checkout: walk up from the installed package directory until
       one containing ``schemas/``, ``catalog/`` and ``pyproject.toml`` is
       found -- the last marker keeps a checkout nested inside an unrelated
       directory that happens to also hold data-shaped siblings from
       resolving to that outer directory. Every developer and every test
       runs this way today, with no environment variable set.
    """
    override = os.environ.get(OVERRIDE_VARIABLE)
    if override:
        return Path(override)

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    packaged = _PACKAGE_DIRECTORY / _PACKAGED_RESOURCES_DIRECTORY_NAME
    if packaged.is_dir():
        return packaged

    return _find_source_checkout_root(_PACKAGE_DIRECTORY)


def _find_source_checkout_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        # `pyproject.toml` on top of the two data directories: without it, a
        # checkout nested inside an unrelated directory that happens to also
        # hold `schemas/` and `catalog/` siblings resolves to that outer
        # directory instead -- silently serving a decoy's data.
        if (
            (candidate / "schemas").is_dir()
            and (candidate / "catalog").is_dir()
            and (candidate / "pyproject.toml").is_file()
        ):
            return candidate
    # No developer or test environment reaches here: every checkout that can
    # import this module has both directories somewhere above it. Returning
    # the starting point keeps this function total -- the resources it
    # implies simply do not exist, and `missing_resources()` reports that by
    # name instead of this function raising.
    return start


def schemas_directory() -> Path:
    return resource_root() / _SCHEMAS_RELATIVE


def catalog_index_path() -> Path:
    return resource_root() / _CATALOG_INDEX_RELATIVE


def compatibility_matrix_path() -> Path:
    return resource_root() / _COMPATIBILITY_MATRIX_RELATIVE


def material_overlay_directory() -> Path:
    return resource_root() / _MATERIAL_OVERLAY_RELATIVE


def active_override() -> str | None:
    """The override's current value, or ``None`` -- so a startup refusal can
    name it. A mis-set override produces a confusing failure otherwise: the
    engineer who set it needs to see that it is the reason, not guess."""
    return os.environ.get(OVERRIDE_VARIABLE) or None


def missing_resources() -> tuple[MissingResource, ...]:
    """Every shipped resource that does not resolve, all at once.

    A user with three missing files must learn that on one launch, not
    across three: this checks all four before returning anything.
    """
    checks: tuple[tuple[str, Path, bool], ...] = (
        ("schemas directory", schemas_directory(), schemas_directory().is_dir()),
        ("catalog index", catalog_index_path(), catalog_index_path().is_file()),
        (
            "compatibility matrix",
            compatibility_matrix_path(),
            compatibility_matrix_path().is_file(),
        ),
        (
            "material overlay directory",
            material_overlay_directory(),
            material_overlay_directory().is_dir(),
        ),
    )
    return tuple(MissingResource(name, path) for name, path, present in checks if not present)
