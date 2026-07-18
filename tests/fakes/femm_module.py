from __future__ import annotations

from pathlib import Path
from typing import Any


class FakeFemmModule:
    """Records every pyfemm call as ``(name, args)``. ``raise_on`` injects a failure."""

    def __init__(self, raise_on: str | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.raise_on = raise_on

    def _record(self, name: str, *args: Any) -> Any:
        if self.raise_on == name:
            raise RuntimeError(f"boom in {name}")
        self.calls.append((name, args))
        if name == "mo_getcircuitproperties":
            return (2 + 0j, 0.2 + 0.126j, 1e-4 + 0j)
        return None

    def openfemm(self, *args: Any) -> Any:
        return self._record("openfemm", *args)

    def newdocument(self, *args: Any) -> Any:
        return self._record("newdocument", *args)

    def mi_probdef(self, *args: Any) -> Any:
        return self._record("mi_probdef", *args)

    def mi_addnode(self, *args: Any) -> Any:
        return self._record("mi_addnode", *args)

    def mi_addarc(self, *args: Any) -> Any:
        return self._record("mi_addarc", *args)

    def mi_addblocklabel(self, *args: Any) -> Any:
        return self._record("mi_addblocklabel", *args)

    def mi_addmaterial(self, *args: Any) -> Any:
        return self._record("mi_addmaterial", *args)

    def mi_addbhpoint(self, *args: Any) -> Any:
        return self._record("mi_addbhpoint", *args)

    def mi_addcircprop(self, *args: Any) -> Any:
        return self._record("mi_addcircprop", *args)

    def mi_selectlabel(self, *args: Any) -> Any:
        return self._record("mi_selectlabel", *args)

    def mi_setblockprop(self, *args: Any) -> Any:
        return self._record("mi_setblockprop", *args)

    def mi_clearselected(self, *args: Any) -> Any:
        return self._record("mi_clearselected", *args)

    def mi_makeABC(self, *args: Any) -> Any:  # noqa: N802 - matches FEMM API casing
        return self._record("mi_makeABC", *args)

    def mi_zoomnatural(self, *args: Any) -> Any:
        return self._record("mi_zoomnatural", *args)

    def mi_saveas(self, *args: Any) -> Any:
        result = self._record("mi_saveas", *args)
        Path(str(args[0])).touch()
        return result

    def mi_analyze(self, *args: Any) -> Any:
        return self._record("mi_analyze", *args)

    def mi_loadsolution(self, *args: Any) -> Any:
        return self._record("mi_loadsolution", *args)

    def mo_getcircuitproperties(self, *args: Any) -> Any:
        return self._record("mo_getcircuitproperties", *args)

    def closefemm(self, *args: Any) -> Any:
        return self._record("closefemm", *args)


class FakeFemmModuleFactory:
    """Records creation and returns a single shared fake module instance."""

    def __init__(self, module: FakeFemmModule) -> None:
        self.module = module
        self.created = 0

    def create(self) -> FakeFemmModule:
        self.created += 1
        return self.module
