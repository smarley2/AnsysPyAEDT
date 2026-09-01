from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    # Release version 0.1.0, ruled 2026-09-01 and applied in M10 Task 4: both
    # `__about__.py` and the editable install's metadata (refreshed via
    # `pip install -e . --no-deps`) must agree, or this assertion fails
    # against a stale value on one side or the other.
    assert inductor_designer.__version__ == "0.1.0"
