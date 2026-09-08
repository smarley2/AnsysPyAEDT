"""Skip marks for tests that need an optional extra the CI runners omit.

The hosted runners install `.[dev,ui]`, so pyaedt (the `aedt` extra) and
PyInstaller (the `packaging` extra) are absent there. A handful of tests check
what the machine that BUILDS the frozen bundle has -- can PyAEDT be imported,
did its data files reach the spec -- and where the extra is absent there is
nothing to check rather than something failing.

`installed()` exists because `importlib.util.find_spec` is not the safe probe
it looks like: for a DOTTED name it imports the parent package first and lets
`ModuleNotFoundError` out, so a bare `find_spec("ansys.aedt.core") is None`
raises at collection time on exactly the runners the mark was written for --
which is what it did, turning four skips into two collection errors. Only a
top-level name returns None.
"""

from __future__ import annotations

import importlib.util

import pytest


def installed(module: str) -> bool:
    """Is `module` importable, without importing it and without raising?"""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        # ImportError covers the missing-parent case above. ValueError is what
        # a partially initialised module in `sys.modules` raises (`__spec__`
        # is None), which is not this project's situation but is equally not a
        # reason to fail collection.
        return False


needs_pyaedt = pytest.mark.skipif(
    not installed("ansys.aedt.core"),
    reason='requires the "aedt" extra (pyaedt)',
)

needs_pyinstaller = pytest.mark.skipif(
    not installed("PyInstaller"),
    reason='requires the "packaging" extra (pyinstaller)',
)
