from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    # Release version 0.4.0, 2026-09-04. Same rule as 0.2.0 and 0.3.0 before
    # it, applied to itself: 0.3.0's installer was compiled and its hash
    # handed over, then conductor provenance, core promotion and the solver
    # import check landed on top -- so these bytes get their own number. One
    # version, one set of bytes, or SHA256SUMS.txt cannot answer the only
    # question it exists for.
    #
    # Both `__about__.py` and the editable install's metadata (refreshed via
    # `pip install -e . --no-deps`) must agree, or this assertion fails
    # against a stale value on one side or the other.
    assert inductor_designer.__version__ == "0.4.0"
