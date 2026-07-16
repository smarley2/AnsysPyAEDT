from __future__ import annotations

from typing import Any


class _Recorder:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], prefix: str) -> None:
        self._log = log
        self._prefix = prefix

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> Any:
            merged = dict(kwargs)
            if args:
                merged["_args"] = args
            self._log.append((f"{self._prefix}{name}", merged))
            return f"{self._prefix}{name}-result"

        return record

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._log.append((f"{self._prefix}set.{name}", {"value": value}))


class _FakeMaterial:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self._name = name

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._log.append((f"material.set.{name}", {"material": self._name, "value": value}))


class _FakeMaterials:
    def __init__(self, log: list[tuple[str, dict[str, Any]]]) -> None:
        self._log = log

    def add_material(self, name: str) -> _FakeMaterial:
        self._log.append(("materials.add_material", {"name": name}))
        return _FakeMaterial(self._log, name)


class _FakeSetup:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self.props: dict[str, Any] = {}
        self._name = name

    def update(self) -> bool:
        self._log.append(("setup.update", {"name": self._name, "props": dict(self.props)}))
        return True


class FakeMaxwell3dApp:
    """Duck-typed Maxwell3d recorder. ``raise_on`` maps a method name to an error."""

    def __init__(self, raise_on: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.raise_on = raise_on
        self.modeler = _Recorder(self.calls, "modeler.")
        self.mesh = _Recorder(self.calls, "mesh.")
        self.post = _Recorder(self.calls, "post.")
        self.materials = _FakeMaterials(self.calls)
        self.released: list[tuple[bool, bool]] = []

    def _record(self, _name: str, **kwargs: Any) -> Any:
        if self.raise_on == _name:
            raise RuntimeError(f"boom in {_name}")
        self.calls.append((_name, kwargs))
        return True

    def assign_material(self, assignment: Any, material: str) -> Any:
        return self._record("assign_material", assignment=assignment, material=material)

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("assign_coil", assignment=assignment, **kwargs)

    def assign_winding(self, assignment: Any = None, **kwargs: Any) -> Any:
        return self._record("assign_winding", assignment=assignment, **kwargs)

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any:
        return self._record("add_winding_coils", assignment=assignment, coils=coils)

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("eddy_effects_on", assignment=assignment, **kwargs)

    def create_setup(self, name: str) -> _FakeSetup:
        if self.raise_on == "create_setup":
            raise RuntimeError("boom in create_setup")
        self.calls.append(("create_setup", {"name": name}))
        return _FakeSetup(self.calls, name)

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("assign_matrix", assignment=assignment, **kwargs)

    def validate_full_design(self) -> tuple[list[str], bool]:
        if self.raise_on == "validate_full_design":
            raise RuntimeError("boom in validate_full_design")
        self.calls.append(("validate_full_design", {}))
        return ([], True)

    def save_project(self, path: str) -> bool:
        if self.raise_on == "save_project":
            raise RuntimeError("boom in save_project")
        self.calls.append(("save_project", {"path": path}))
        return True

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None:
        self.released.append((close_projects, close_desktop))


class FakeMaxwell3dAppFactory:
    pyaedt_version = "fake-pyaedt"

    def __init__(self, app: FakeMaxwell3dApp) -> None:
        self.app = app
        self.create_kwargs: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeMaxwell3dApp:
        self.create_kwargs.append(kwargs)
        return self.app
