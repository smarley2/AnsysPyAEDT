from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any, Protocol, cast

from inductor_designer.application.ports.femm_solver import (
    FemmSolveRequest,
    FemmSolveResult,
    FemmWindingResult,
)

_NONE_CIRCUIT = "<None>"
_AIR_MATERIAL = "Air"


class FemmModule(Protocol):
    def openfemm(self, *args: Any) -> Any: ...

    def newdocument(self, *args: Any) -> Any: ...

    def mi_probdef(self, *args: Any) -> Any: ...

    def mi_addnode(self, *args: Any) -> Any: ...

    def mi_addarc(self, *args: Any) -> Any: ...

    def mi_addblocklabel(self, *args: Any) -> Any: ...

    def mi_addmaterial(self, *args: Any) -> Any: ...

    def mi_addcircprop(self, *args: Any) -> Any: ...

    def mi_selectlabel(self, *args: Any) -> Any: ...

    def mi_setblockprop(self, *args: Any) -> Any: ...

    def mi_clearselected(self, *args: Any) -> Any: ...

    def mi_makeABC(self, *args: Any) -> Any: ...  # noqa: N802 - matches FEMM API casing

    def mi_zoomnatural(self, *args: Any) -> Any: ...

    def mi_saveas(self, *args: Any) -> Any: ...

    def mi_analyze(self, *args: Any) -> Any: ...

    def mi_loadsolution(self, *args: Any) -> Any: ...

    def mo_getcircuitproperties(self, *args: Any) -> Any: ...

    def closefemm(self, *args: Any) -> Any: ...


class FemmModuleFactory(Protocol):
    def create(self) -> FemmModule: ...


class DefaultFemmModuleFactory:
    def create(self) -> FemmModule:
        import femm

        return cast(FemmModule, femm)


def _add_circle(femm: FemmModule, x: float, y: float, r: float) -> None:
    femm.mi_addnode(x - r, y)
    femm.mi_addnode(x + r, y)
    femm.mi_addarc(x - r, y, x + r, y, 180, 5)
    femm.mi_addarc(x + r, y, x - r, y, 180, 5)


def _add_block_label(
    femm: FemmModule, x: float, y: float, material: str, circuit: str, turns: int
) -> None:
    femm.mi_addblocklabel(x, y)
    femm.mi_selectlabel(x, y)
    femm.mi_setblockprop(material, 1, 0, circuit, 0, 0, turns)
    femm.mi_clearselected()


class PyfemmSolver:
    """Builds an axisymmetric-free planar FEMM model and extracts circuit impedances."""

    def __init__(self, module_factory: FemmModuleFactory | None = None) -> None:
        self._factory = DefaultFemmModuleFactory() if module_factory is None else module_factory

    def solve(self, request: FemmSolveRequest) -> FemmSolveResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        fem_path = request.output_directory / f"{request.project_name}.fem"
        problem = request.problem
        messages: list[str] = []
        results: dict[str, FemmWindingResult] | None = None

        femm = self._factory.create()
        try:
            femm.openfemm(1)
            femm.newdocument(0)
            femm.mi_probdef(problem.frequency_hz, "meters", "planar", 1e-8, problem.depth_m, 30)
            messages.append(f"Problem defined at {problem.frequency_hz:g} Hz.")

            for material in problem.materials:
                femm.mi_addmaterial(
                    material.name,
                    material.relative_permeability,
                    material.relative_permeability,
                    0,
                    0,
                    material.conductivity_ms_per_m,
                    0,
                    0,
                    1,
                    0,
                    0,
                    0,
                )
            messages.append(f"{len(problem.materials)} materials added.")

            phase_deferred = False
            for circuit in problem.circuits:
                femm.mi_addcircprop(circuit.name, circuit.current_peak_a, 1)
                if circuit.phase_deg != 0.0:
                    phase_deferred = True
            messages.append(f"{len(problem.circuits)} circuits added.")
            if phase_deferred:
                messages.append(
                    "Circuit phase not applied; deferred pending live FEMM verification."
                )

            _add_circle(femm, 0.0, 0.0, problem.core.r_outer_m)
            _add_circle(femm, 0.0, 0.0, problem.core.r_inner_m)
            for conductor in problem.conductors:
                _add_circle(femm, conductor.x_m, conductor.y_m, conductor.radius_m)
            messages.append(f"Geometry built: core + {len(problem.conductors)} conductor(s).")

            for conductor in problem.conductors:
                _add_block_label(
                    femm,
                    conductor.x_m,
                    conductor.y_m,
                    conductor.material,
                    conductor.circuit,
                    conductor.turns,
                )
            core_x = (problem.core.r_inner_m + problem.core.r_outer_m) / 2.0
            _add_block_label(femm, core_x, 0.0, problem.core.material, _NONE_CIRCUIT, 0)
            _add_block_label(femm, 0.0, 0.0, _AIR_MATERIAL, _NONE_CIRCUIT, 0)
            _add_block_label(
                femm, 0.0, problem.core.r_outer_m * 1.5, _AIR_MATERIAL, _NONE_CIRCUIT, 0
            )
            messages.append("Block labels assigned.")

            femm.mi_makeABC()
            femm.mi_zoomnatural()

            femm.mi_saveas(str(fem_path))
            if not fem_path.exists():
                raise RuntimeError(f"mi_saveas did not create {fem_path}")
            messages.append(f"Saved {fem_path}.")

            if request.analyze:
                femm.mi_analyze(1)
                femm.mi_loadsolution()
                results = {}
                for circuit in problem.circuits:
                    props = femm.mo_getcircuitproperties(circuit.name)
                    if (
                        isinstance(props, (str, bytes))
                        or not isinstance(props, Sequence)
                        or len(props) != 3
                    ):
                        raise RuntimeError(
                            f"mo_getcircuitproperties({circuit.name!r}) returned "
                            f"an unexpected value: {props!r}"
                        )
                    current, voltage, flux = props
                    if abs(current) == 0.0:
                        raise RuntimeError(
                            f"Circuit {circuit.name!r} returned zero current; "
                            "cannot derive impedance."
                        )
                    impedance = voltage / current
                    resistance = round(impedance.real, 9)
                    inductance = round(
                        impedance.imag / (2 * math.pi * problem.frequency_hz), 9
                    )
                    results[circuit.name] = FemmWindingResult(
                        resistance_ohm=resistance,
                        inductance_h=inductance,
                        current_a=(current.real, current.imag),
                        voltage_v=(voltage.real, voltage.imag),
                        flux_linkage_wb=(flux.real, flux.imag),
                    )
                messages.append(f"Analyzed; {len(results)} circuit(s) extracted.")
        finally:
            femm.closefemm()

        return FemmSolveResult(
            fem_path=fem_path,
            analyzed=request.analyze,
            results=results,
            messages=tuple(messages),
        )
