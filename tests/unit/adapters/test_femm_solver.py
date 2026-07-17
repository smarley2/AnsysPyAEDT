from __future__ import annotations

import math
from pathlib import Path

import pytest

from inductor_designer.adapters.femm.solver import PyfemmSolver
from inductor_designer.application.ports.femm_solver import FemmSolveRequest
from inductor_designer.simulation.femm_problem import femm_problem_from_plan
from tests.fakes.femm_module import FakeFemmModule, FakeFemmModuleFactory
from tests.unit.simulation.test_maxwell_plan import make_approved_material_record
from tests.unit.simulation.test_plan_builder import make_definition
from tests.unit.simulation.test_plan_builder2d import build2d


def make_request(tmp_path: Path, analyze: bool = True) -> FemmSolveRequest:
    plan = build2d((make_definition(),))  # type: ignore[arg-type]
    problem = femm_problem_from_plan(plan)
    return FemmSolveRequest(
        problem=problem,
        output_directory=tmp_path,
        project_name="test_inductor",
        analyze=analyze,
    )


def run(
    tmp_path: Path, analyze: bool = True, raise_on: str | None = None
) -> tuple[object, FakeFemmModule]:
    module = FakeFemmModule(raise_on=raise_on)
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))
    request = make_request(tmp_path, analyze=analyze)
    result = solver.solve(request)
    return result, module


def test_fem_path_and_saveas(tmp_path: Path) -> None:
    result, module = run(tmp_path)
    assert result.fem_path == tmp_path / "test_inductor.fem"  # type: ignore[attr-defined]
    assert result.fem_path.exists()  # type: ignore[attr-defined]
    names = [name for name, _ in module.calls]
    assert "mi_saveas" in names


def test_call_order_probdef_before_geometry_and_makeabc_before_saveas(tmp_path: Path) -> None:
    _, module = run(tmp_path)
    names = [name for name, _ in module.calls]
    assert names.index("mi_probdef") < names.index("mi_addnode")
    assert names.index("mi_makeABC") < names.index("mi_saveas")
    assert names.index("openfemm") < names.index("newdocument") < names.index("mi_probdef")
    assert names.index("mi_saveas") < names.index("mi_analyze")


def test_analyze_false_skips_analyze_and_yields_none_results(tmp_path: Path) -> None:
    result, module = run(tmp_path, analyze=False)
    names = [name for name, _ in module.calls]
    assert "mi_analyze" not in names
    assert "mi_loadsolution" not in names
    assert "mo_getcircuitproperties" not in names
    assert result.analyzed is False  # type: ignore[attr-defined]
    assert result.results is None  # type: ignore[attr-defined]


def test_signed_turns_forwarded_to_setblockprop(tmp_path: Path) -> None:
    _, module = run(tmp_path)
    setblockprop_calls = [args for name, args in module.calls if name == "mi_setblockprop"]
    turns = {call[-1] for call in setblockprop_calls}
    assert turns == {1, -1, 0}


def test_nonlinear_bh_points_are_added_after_material(tmp_path: Path) -> None:
    plan = build2d(
        (make_definition(),), material_record=make_approved_material_record()
    )
    problem = femm_problem_from_plan(plan)  # type: ignore[arg-type]
    request = FemmSolveRequest(
        problem=problem,
        output_directory=tmp_path,
        project_name="nonlinear_inductor",
        analyze=False,
    )
    module = FakeFemmModule()
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))

    solver.solve(request)

    material_name = plan.core.material.name
    assert ("mi_addbhpoints", (material_name, [[0.0, 0.0], [0.025132741, 100.0]])) in module.calls
    names = [name for name, _ in module.calls]
    assert names.index("mi_addmaterial") < names.index("mi_addbhpoints")


def test_resistance_and_inductance_math(tmp_path: Path) -> None:
    result, _ = run(tmp_path)
    assert result.results is not None  # type: ignore[attr-defined]
    for winding_result in result.results.values():  # type: ignore[attr-defined]
        assert winding_result.resistance_ohm == 0.1
        expected_l = round(0.063 / (2 * math.pi * 100_000.0), 9)
        assert winding_result.inductance_h == expected_l
        assert winding_result.current_a == (2.0, 0.0)
        assert winding_result.voltage_v == (0.2, 0.126)
        assert winding_result.flux_linkage_wb == (1e-4, 0.0)


def test_closefemm_called_even_when_a_call_raises(tmp_path: Path) -> None:
    module = FakeFemmModule(raise_on="mi_makeABC")
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))
    request = make_request(tmp_path)
    with pytest.raises(RuntimeError):
        solver.solve(request)
    names = [name for name, _ in module.calls]
    assert "closefemm" in names


def test_factory_creation_recorded(tmp_path: Path) -> None:
    module = FakeFemmModule()
    factory = FakeFemmModuleFactory(module)
    solver = PyfemmSolver(module_factory=factory)
    solver.solve(make_request(tmp_path))
    assert factory.created == 1


def test_mo_getcircuitproperties_bad_return_raises(tmp_path: Path) -> None:
    module = FakeFemmModule()

    def bad_props(*_args: object) -> object:
        return None

    module.mo_getcircuitproperties = bad_props  # type: ignore[method-assign]
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))
    with pytest.raises(RuntimeError):
        solver.solve(make_request(tmp_path))


def test_zero_current_raises_runtime_error(tmp_path: Path) -> None:
    module = FakeFemmModule()

    def zero_current_props(*_args: object) -> object:
        return (0j, 0.2 + 0.126j, 0j)

    module.mo_getcircuitproperties = zero_current_props  # type: ignore[method-assign]
    solver = PyfemmSolver(module_factory=FakeFemmModuleFactory(module))
    with pytest.raises(RuntimeError, match="zero current"):
        solver.solve(make_request(tmp_path))


def test_air_background_labels_at_origin_and_outside_core(tmp_path: Path) -> None:
    plan = build2d((make_definition(),))  # type: ignore[arg-type]
    problem = femm_problem_from_plan(plan)
    _, module = run(tmp_path)

    label_calls = [args for name, args in module.calls if name == "mi_addblocklabel"]
    setprop_calls = [args for name, args in module.calls if name == "mi_setblockprop"]
    air_pairs = [
        (label, prop)
        for label, prop in zip(label_calls, setprop_calls, strict=True)
        if prop[0] == "Air"
    ]

    assert len(air_pairs) == 2
    positions = sorted((label[0], label[1]) for label, _ in air_pairs)
    expected = sorted([(0.0, 0.0), (0.0, problem.core.r_outer_m * 1.5)])
    assert positions == expected
