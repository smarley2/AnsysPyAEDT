from pathlib import Path

from tools.check_architecture import Violation, find_forbidden_imports


def test_finds_forbidden_dependency_in_inner_package(tmp_path: Path) -> None:
    source = tmp_path / "inductor_designer" / "domain" / "model.py"
    source.parent.mkdir(parents=True)
    source.write_text("from ansys.aedt.core import Maxwell3d\n", encoding="utf-8")

    assert find_forbidden_imports(tmp_path) == (
        Violation(source, 1, "ansys.aedt.core", "domain"),
    )


def test_repository_inner_packages_respect_boundaries() -> None:
    assert find_forbidden_imports(Path("src")) == ()
