from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    # Release version 0.3.0, ruled 2026-09-04: 0.2.0's installer was already
    # built and its hash handed over, and this build adds core import on top,
    # so it must not wear that number -- one version, one set of bytes, or the
    # checksums file cannot answer the only question it exists for. 0.2.0
    # itself was ruled on 2026-09-03 for the same reason against 0.1.0, whose
    # shortcut launch could neither open nor create a project.
    #
    # Both `__about__.py` and the editable install's metadata (refreshed via
    # `pip install -e . --no-deps`) must agree, or this assertion fails
    # against a stale value on one side or the other.
    assert inductor_designer.__version__ == "0.3.0"
