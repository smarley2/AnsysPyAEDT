from importlib.metadata import version

import inductor_designer


def test_package_exposes_installed_version() -> None:
    assert inductor_designer.__version__ == version("pyaedt-inductor-designer")
    assert inductor_designer.__version__ == "0.1.0.dev0"
