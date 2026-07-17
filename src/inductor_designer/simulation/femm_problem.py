from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import Polarity

COPPER_CONDUCTIVITY_MS_PER_M = 58.0
AIR_MATERIAL = "Air"
_SOLID_COPPER_MATERIAL = "Copper_solid"
_STRANDED_COPPER_MATERIAL = "Copper_stranded"


@dataclass(frozen=True, slots=True)
class FemmMaterial:
    name: str
    relative_permeability: float
    conductivity_ms_per_m: float
    bh_points: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class FemmCircuit:
    name: str
    current_peak_a: float
    phase_deg: float


@dataclass(frozen=True, slots=True)
class FemmConductor:
    x_m: float
    y_m: float
    radius_m: float
    material: str
    circuit: str
    turns: int

    def __post_init__(self) -> None:
        if not self.radius_m > 0.0:
            raise ValueError("FemmConductor radius_m must be positive")
        if self.turns not in (-1, 1):
            raise ValueError("FemmConductor turns must be -1 or 1")


@dataclass(frozen=True, slots=True)
class FemmAnnulus:
    r_inner_m: float
    r_outer_m: float
    material: str

    def __post_init__(self) -> None:
        if not 0.0 < self.r_inner_m < self.r_outer_m:
            raise ValueError("FemmAnnulus requires 0 < r_inner_m < r_outer_m")


@dataclass(frozen=True, slots=True)
class FemmProblem:
    frequency_hz: float
    depth_m: float
    core: FemmAnnulus
    materials: tuple[FemmMaterial, ...]
    circuits: tuple[FemmCircuit, ...]
    conductors: tuple[FemmConductor, ...]

    def __post_init__(self) -> None:
        if not self.frequency_hz > 0.0:
            raise ValueError("FemmProblem frequency_hz must be positive")
        if not self.depth_m > 0.0:
            raise ValueError("FemmProblem depth_m must be positive")


def femm_problem_from_plan(plan: Maxwell2dDesignPlan) -> FemmProblem:
    materials = [
        FemmMaterial(AIR_MATERIAL, relative_permeability=1.0, conductivity_ms_per_m=0.0),
        FemmMaterial(
            plan.core.material.name,
            relative_permeability=plan.core.material.relative_permeability,
            conductivity_ms_per_m=0.0,
            bh_points=plan.core.material.bh_curve,
        ),
    ]
    has_solid = any(winding.is_solid for winding in plan.windings)
    has_stranded = any(not winding.is_solid for winding in plan.windings)
    if has_solid:
        materials.append(
            FemmMaterial(
                _SOLID_COPPER_MATERIAL,
                relative_permeability=1.0,
                conductivity_ms_per_m=COPPER_CONDUCTIVITY_MS_PER_M,
            )
        )
    if has_stranded:
        materials.append(
            FemmMaterial(
                _STRANDED_COPPER_MATERIAL,
                relative_permeability=1.0,
                conductivity_ms_per_m=0.0,
            )
        )

    circuits = tuple(
        FemmCircuit(winding.name, winding.current_peak_a, winding.phase_deg)
        for winding in plan.windings
    )

    conductors = tuple(
        FemmConductor(
            x_m=conductor.x_m,
            y_m=conductor.y_m,
            radius_m=conductor.radius_m,
            material=_SOLID_COPPER_MATERIAL if winding.is_solid else _STRANDED_COPPER_MATERIAL,
            circuit=winding.name,
            turns=1 if conductor.polarity is Polarity.POSITIVE else -1,
        )
        for winding in plan.windings
        for conductor in winding.conductors
    )

    return FemmProblem(
        frequency_hz=plan.setup.frequency_hz,
        depth_m=plan.model_depth_m,
        core=FemmAnnulus(
            r_inner_m=plan.core.r_inner_m,
            r_outer_m=plan.core.r_outer_m,
            material=plan.core.material.name,
        ),
        materials=tuple(materials),
        circuits=circuits,
        conductors=conductors,
    )
