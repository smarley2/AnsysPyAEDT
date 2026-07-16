from __future__ import annotations

import pytest

from inductor_designer.simulation.maxwell2d_plan import Core2dPlan, Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import (
    MATRIX_NAME,
    MaterialSpec,
    MeshPlan,
    RegionPlan,
    SetupPlan,
)

MATERIAL = MaterialSpec(
    name="Magnetics_Kool_Mu_60", relative_permeability=60.0, conductivity_s_per_m=0.0, draft=False
)


def test_core_plan_validates_radii() -> None:
    with pytest.raises(ValueError, match="r_inner"):
        Core2dPlan(name="Core", r_inner_m=0.02, r_outer_m=0.01, material=MATERIAL)


def test_design_plan_validates_depth() -> None:
    with pytest.raises(ValueError, match="model_depth"):
        Maxwell2dDesignPlan(
            design_name="Inductor2D",
            solution_type="EddyCurrent",
            model_depth_m=0.0,
            core=Core2dPlan(name="Core", r_inner_m=0.01, r_outer_m=0.02, material=MATERIAL),
            windings=(),
            region=RegionPlan(padding_percent=100.0),
            mesh=MeshPlan(conductor_max_length_m=0.001, core_max_length_m=0.003),
            setup=SetupPlan(name="Setup1", frequency_hz=1e5, maximum_passes=10, percent_error=1.0),
            matrix_name=MATRIX_NAME,
            reports=(),
            notes=(),
        )
