"""The optional-extra probe, pinned against the mistake it was written after.

`installed()` replaced a bare `importlib.util.find_spec("ansys.aedt.core") is
None`, which raises `ModuleNotFoundError` when the parent package `ansys` is
absent -- so on exactly the CI runners the skip marks were written for, four
skips became two collection errors and the whole test job exited 2.
"""

from __future__ import annotations

import pytest

from tests.optional_extras import installed, needs_pyaedt, needs_pyinstaller


def test_a_dotted_name_whose_parent_is_absent_is_reported_absent() -> None:
    """The bug: `find_spec` imports the parent of a dotted name and lets
    `ModuleNotFoundError` out. Bare `find_spec` here raises instead of
    answering."""
    assert installed("no_such_top_level_package_xyz.sub.module") is False


def test_a_missing_top_level_name_is_reported_absent() -> None:
    assert installed("no_such_top_level_package_xyz") is False


def test_a_present_module_is_reported_present() -> None:
    assert installed("json") is True
    assert installed("json.decoder") is True


@pytest.mark.parametrize("mark", [needs_pyaedt, needs_pyinstaller])
def test_each_mark_carries_a_condition_and_a_reason(mark: pytest.MarkDecorator) -> None:
    """A mark built from a raising expression never gets this far -- import of
    this module would have failed -- so this also pins that the marks are
    constructible where the extras are absent."""
    assert mark.mark.name == "skipif"
    assert isinstance(mark.mark.args[0], bool)
    assert "extra" in mark.mark.kwargs["reason"]
