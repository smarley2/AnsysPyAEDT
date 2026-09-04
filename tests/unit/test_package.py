from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    # Release version 0.2.0, ruled 2026-09-03: 0.1.0 shipped an application
    # whose shortcut launch could neither open nor create a project, so the
    # build that fixes it must not wear the same version number -- two
    # different builds called 0.1.0 is exactly the confusion the checksums
    # file exists to prevent. `File > New` also makes it a feature release
    # rather than a patch.
    #
    # Both `__about__.py` and the editable install's metadata (refreshed via
    # `pip install -e . --no-deps`) must agree, or this assertion fails
    # against a stale value on one side or the other.
    assert inductor_designer.__version__ == "0.2.0"
