from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    # Release version 0.1.0 is ruled (2026-09-01) but not yet applied: bumping
    # `__about__.py` also needs the editable install's metadata refreshed, or
    # this assertion fails against a stale `0.1.0.dev0`. Done as its own step in
    # M10 Task 3, where the packaging build owns the version.
