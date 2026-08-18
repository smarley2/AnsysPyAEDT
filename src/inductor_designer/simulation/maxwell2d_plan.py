from __future__ import annotations

from dataclasses import dataclass

from inductor_designer.simulation.capabilities import DcBiasDecision
from inductor_designer.simulation.maxwell_plan import (
    MaterialSpec,
    MeshPlan,
    Polarity,
    RegionPlan,
    ReportPlan,
    SetupPlan,
)

DESIGN_NAME_2D = "Inductor2D"


@dataclass(frozen=True, slots=True)
class Conductor2dPlan:
    """One circular conductor region of the XY cross-section (go or return)."""

    name: str
    x_m: float
    y_m: float
    radius_m: float
    polarity: Polarity


@dataclass(frozen=True, slots=True)
class Winding2dGroupPlan:
    name: str
    winding_id: str
    is_solid: bool
    current_peak_a: float
    phase_deg: float
    dc_current_a: float
    conductors: tuple[Conductor2dPlan, ...]
    # Length of one real turn, which the cross-section cannot show. The XY model
    # represents the whole magnetic circuit -- azimuthal path, full core height
    # as the model depth -- but only the two axial legs of each turn's copper,
    # so its resistance covers `2 * model_depth` per turn where the real turn
    # also runs radially across the top and bottom faces. Carried here so the
    # result path can state, and correct for, that difference. 0.0 means the
    # caller supplied no packing length.
    turn_length_m: float = 0.0


@dataclass(frozen=True, slots=True)
class Core2dPlan:
    name: str
    r_inner_m: float
    r_outer_m: float
    material: MaterialSpec

    def __post_init__(self) -> None:
        if not 0.0 < self.r_inner_m < self.r_outer_m:
            raise ValueError("Core2dPlan requires 0 < r_inner_m < r_outer_m")


@dataclass(frozen=True, slots=True)
class Maxwell2dDesignPlan:
    design_name: str
    solution_type: str
    model_depth_m: float
    core: Core2dPlan
    windings: tuple[Winding2dGroupPlan, ...]
    region: RegionPlan
    mesh: MeshPlan
    setup: SetupPlan
    matrix_name: str
    reports: tuple[ReportPlan, ...]
    notes: tuple[str, ...]
    dc_bias: DcBiasDecision | None = None

    def __post_init__(self) -> None:
        if not self.model_depth_m > 0.0:
            raise ValueError("Maxwell2dDesignPlan model_depth_m must be positive")
