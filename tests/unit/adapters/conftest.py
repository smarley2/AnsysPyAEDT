from __future__ import annotations

import sys
from dataclasses import dataclass
from types import ModuleType

import pytest


@pytest.fixture()
def fake_maxwell_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the optional PyAEDT matrix schemas to adapter unit tests."""

    @dataclass(frozen=True)
    class SourceACMagnetic:
        name: str

    @dataclass(frozen=True)
    class MatrixACMagnetic:
        signal_sources: list[SourceACMagnetic]
        matrix_name: str

    module_names = (
        "ansys",
        "ansys.aedt",
        "ansys.aedt.core",
        "ansys.aedt.core.modules",
        "ansys.aedt.core.modules.boundary",
    )
    for module_name in module_names:
        module = ModuleType(module_name)
        module.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, module_name, module)

    boundary = ModuleType("ansys.aedt.core.modules.boundary.maxwell_boundary")
    boundary.MatrixACMagnetic = MatrixACMagnetic  # type: ignore[attr-defined]
    boundary.SourceACMagnetic = SourceACMagnetic  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "ansys.aedt.core.modules.boundary.maxwell_boundary",
        boundary,
    )
