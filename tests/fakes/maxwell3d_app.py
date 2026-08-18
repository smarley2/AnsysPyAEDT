from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _FakeRegion:
    edges: list[str] = field(
        default_factory=lambda: ["Region_edge1", "Region_edge2", "Region_edge3", "Region_edge4"]
    )


class _Recorder:
    def __init__(
        self,
        log: list[tuple[str, dict[str, Any]]],
        prefix: str,
        falsy_on: str | None = None,
        raise_on: str | None = None,
    ) -> None:
        self._log = log
        self._prefix = prefix
        self._falsy_on = falsy_on
        self._raise_on = raise_on

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> Any:
            if self._raise_on == name:
                raise RuntimeError(f"boom in {name}")
            merged = dict(kwargs)
            if args:
                merged["_args"] = args
            self._log.append((f"{self._prefix}{name}", merged))
            if self._falsy_on == name:
                return None
            if name == "create_region":
                return _FakeRegion()
            return f"{self._prefix}{name}-result"

        return record

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._log.append((f"{self._prefix}set.{name}", {"value": value}))


class _FakeMaterial:
    def __init__(
        self,
        log: list[tuple[str, dict[str, Any]]],
        name: str,
        coreloss_result: bool,
    ) -> None:
        self._log = log
        self._name = name
        self._coreloss_result = coreloss_result
        # Real PyAEDT materials expose _props plus update(); the adapter rewrites
        # the Steinmetz unit strings through them.
        self._props: dict[str, Any] = {}

    def update(self) -> bool:
        self._log.append(
            ("material.update", {"material": self._name, "props": dict(self._props)})
        )
        return True

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._log.append((f"material.set.{name}", {"material": self._name, "value": value}))

    def set_power_ferrite_coreloss(self, **kwargs: Any) -> bool:
        self._log.append(
            ("material.set_power_ferrite_coreloss", {"material": self._name, **kwargs})
        )
        if self._coreloss_result:
            # Mirror the PyAEDT defect the adapter corrects: cm and x are stored
            # with bogus unit suffixes (material.py:2937-2938).
            self._props["core_loss_cm"] = f"{kwargs.get('cm')}A_per_meter"
            self._props["core_loss_x"] = f"{kwargs.get('x')}tesla"
            self._props["core_loss_y"] = str(kwargs.get("y"))
        return self._coreloss_result


class _FakeMaterials:
    def __init__(
        self, log: list[tuple[str, dict[str, Any]]], coreloss_result: bool
    ) -> None:
        self._log = log
        self._coreloss_result = coreloss_result

    def add_material(self, name: str) -> _FakeMaterial:
        self._log.append(("materials.add_material", {"name": name}))
        return _FakeMaterial(self._log, name, self._coreloss_result)


class _FakeSetup:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self.props: dict[str, Any] = {}
        self._name = name

    def update(self) -> bool:
        self._log.append(("setup.update", {"name": self._name, "props": dict(self.props)}))
        return True


class _FakeWinding:
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        self._log = log
        self._name = name
        self.props = _PropsProxy(log, name)

    def update(self) -> bool:
        self._log.append(("winding.update", {"name": self._name}))
        return True


class _PropsProxy(dict[str, Any]):
    def __init__(self, log: list[tuple[str, dict[str, Any]]], name: str) -> None:
        super().__init__()
        self._log = log
        self._name = name

    def __setitem__(self, key: str, value: Any) -> None:
        self._log.append(("winding.set_prop", {"name": self._name, "key": key, "value": value}))
        super().__setitem__(key, value)


class _FakeODesign:
    def __init__(
        self,
        log: list[tuple[str, dict[str, Any]]],
        raise_on: str | None = None,
        falsy_on: str | None = None,
    ) -> None:
        self._log = log
        self._raise_on = raise_on
        self._falsy_on = falsy_on

    def GetModule(self, name: str) -> _Recorder:  # noqa: N802 - matches AEDT COM API casing
        return _Recorder(
            self._log,
            f"{name}.",
            falsy_on=self._falsy_on,
            raise_on=self._raise_on,
        )


@dataclass
class _FakeSheet:
    name: str
    non_model: bool
    kind: str


class FakeMaxwell3dApp:
    """Duck-typed Maxwell3d recorder. ``raise_on`` maps a method name to an error."""

    def __init__(
        self,
        raise_on: str | None = None,
        falsy_on: str | None = None,
        coreloss_result: bool = True,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.raise_on = raise_on
        self.falsy_on = falsy_on
        self.analyzed_setups: tuple[str, ...] = ()
        self.analyze_blocking: list[Any] = []
        self.fail_analyze = False
        # AEDT's verdict on a finished solve. A solver that dies mid-way also
        # stops running, so the fake has to be able to say so.
        self.status = "Normal Completion"
        # What the desktop reports on each `are_there_simulations_running`
        # poll; an exhausted list reads as idle, so a plain fake solves
        # instantly. `on_poll` lets a test cancel mid-solve.
        self.running_polls: list[float] = []
        self.polls = 0
        self.stopped: list[bool] = []
        self.on_poll: Callable[[], None] | None = None
        self.fail_solution_values = False
        self.fail_field_value_for: str | None = None
        self.created_sheets: list[_FakeSheet] = []
        # Lets a test act (cancel a run, for example) exactly when the design
        # reaches a named call, without patching the adapter.
        self.on_call: dict[str, Callable[[], None]] = {}
        self.modeler = _Recorder(self.calls, "modeler.", falsy_on=falsy_on)
        self.mesh = _Recorder(self.calls, "mesh.")
        self.post = _Recorder(self.calls, "post.")
        self.materials = _FakeMaterials(self.calls, coreloss_result)
        self.odesign = _FakeODesign(self.calls, raise_on=raise_on, falsy_on=falsy_on)
        self.released: list[tuple[bool, bool]] = []

    def _hook(self, name: str) -> None:
        callback = self.on_call.get(name)
        if callback is not None:
            callback()

    def _record(self, _name: str, **kwargs: Any) -> Any:
        self._hook(_name)
        if self.raise_on == _name:
            raise RuntimeError(f"boom in {_name}")
        self.calls.append((_name, kwargs))
        if self.falsy_on == _name:
            return None
        return True

    def assign_material(self, assignment: Any, material: str) -> Any:
        return self._record("assign_material", assignment=assignment, material=material)

    def set_core_losses(self, assignment: Any, core_loss_on_field: bool = False) -> Any:
        return self._record(
            "set_core_losses",
            assignment=assignment,
            core_loss_on_field=core_loss_on_field,
        )

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("assign_coil", assignment=assignment, **kwargs)

    def assign_winding(self, assignment: Any = None, **kwargs: Any) -> Any:
        if self.raise_on == "assign_winding":
            raise RuntimeError("boom in assign_winding")
        self.calls.append(("assign_winding", {"assignment": assignment, **kwargs}))
        return _FakeWinding(self.calls, str(kwargs.get("name")))

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any:
        return self._record("add_winding_coils", assignment=assignment, coils=coils)

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("eddy_effects_on", assignment=assignment, **kwargs)

    def create_setup(self, name: str) -> _FakeSetup:
        self._hook("create_setup")
        if self.raise_on == "create_setup":
            raise RuntimeError("boom in create_setup")
        self.calls.append(("create_setup", {"name": name}))
        return _FakeSetup(self.calls, name)

    def assign_matrix(self, assignment: Any = None, **kwargs: Any) -> Any:
        return self._record("assign_matrix", assignment=assignment, **kwargs)

    def assign_balloon(self, assignment: Any, **kwargs: Any) -> Any:
        return self._record("assign_balloon", assignment=assignment, **kwargs)

    def validate_simple(self, log_file: str | None = None) -> int:
        self._hook("validate_simple")
        if self.raise_on == "validate_simple":
            raise RuntimeError("boom in validate_simple")
        self.calls.append(("validate_simple", {}))
        return 1

    def analyze_setup(self, name: str, *, blocking: bool = True) -> bool:
        self._hook("analyze_setup")
        if self.fail_analyze:
            raise RuntimeError("Solver returned a nonzero exit code.")
        self.analyzed_setups += (name,)
        self.analyze_blocking.append(blocking)
        self.calls.append(("analyze_setup", {"name": name, "blocking": blocking}))
        return True

    @property
    def are_there_simulations_running(self) -> float:
        self.polls += 1
        if self.on_poll is not None:
            self.on_poll()
        return self.running_polls.pop(0) if self.running_polls else 0.0

    def stop_simulations(self, clean_stop: bool = True) -> str:
        self.stopped.append(clean_stop)
        return "stopped"

    def setup_convergence(self, name: str) -> str:
        return "3 passes, 0.42% error"

    def solve_status(self, name: str) -> str:
        """AEDT's verdict on the finished solve; scripted so a run that died
        mid-solve can be exercised without a solver."""
        return self.status

    def solution_values(self, expressions: tuple[str, ...]) -> dict[str, complex]:
        if self.fail_solution_values:
            raise RuntimeError("Solution data is not available for this setup.")
        values: dict[str, complex] = {
            "SolidLoss": 3.0 + 0j,
            "CoreLoss": 1.25 + 0j,
        }
        # No energy value. An AC Magnetic design exposes no energy report
        # quantity (enumerated live on AEDT 2025 R2 Commercial, 2026-08-18), so
        # answering one here would let the tests assert a capability AEDT does
        # not have.
        for expression in expressions:
            if ".L(" in expression:
                values[expression] = 1e-4 + 0j
            elif ".R(" in expression:
                values[expression] = 0.125 + 0j
        return values

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]:
        return ((1, 12.5), (2, 0.8))

    def create_section_rectangle(
        self,
        name: str,
        azimuth_deg: float,
        r_inner_m: float,
        r_outer_m: float,
        half_height_m: float,
    ) -> str:
        # Honours `raise_on` like every other call, so a test can reproduce the
        # live modeler refusal (`GrpcApiError ... CreateRectangle`).
        self._hook("create_section_rectangle")
        if self.raise_on == "create_section_rectangle":
            raise RuntimeError("boom in create_section_rectangle")
        self.created_sheets.append(_FakeSheet(name=name, non_model=True, kind="rectangle"))
        return name

    def create_section_disc(
        self,
        name: str,
        center_m: tuple[float, float, float],
        normal: tuple[float, float, float],
        radius_m: float,
    ) -> str:
        self._hook("create_section_disc")
        if self.raise_on == "create_section_disc":
            raise RuntimeError("boom in create_section_disc")
        self.created_sheets.append(_FakeSheet(name=name, non_model=True, kind="disc"))
        return name

    def field_value(
        self,
        quantity: str,
        scalar_function: str,
        object_name: str,
        object_type: str,
    ) -> float:
        if self.fail_field_value_for and self.fail_field_value_for in object_name:
            raise RuntimeError(f"no field data on {object_name}")
        # Integral over the sheet, and a point maximum above the mean.
        return 1e-5 if scalar_function == "Integrate" else 0.42

    def save_project(self, path: str) -> bool:
        self._hook("save_project")
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
