from __future__ import annotations

import math
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, cast

from inductor_designer.adapters.pyaedt.polyline_data import polyline_data
from inductor_designer.application.ports.maxwell_exporter import (
    Maxwell3dExportRequest,
    Maxwell3dExportResult,
    StageRecord,
)
from inductor_designer.simulation.maxwell_plan import COPPER_MATERIAL, Maxwell3dDesignPlan


class Maxwell3dApp(Protocol):
    modeler: Any
    mesh: Any
    post: Any
    materials: Any

    def assign_material(self, assignment: Any, material: str) -> Any: ...

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_winding(self, assignment: Any = ..., **kwargs: Any) -> Any: ...

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any: ...

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any: ...

    def create_setup(self, name: str) -> Any: ...

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any: ...

    def validate_simple(self, log_file: str | None = None) -> int: ...

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...


class Maxwell3dAppFactory(Protocol):
    pyaedt_version: str

    def create(self, **kwargs: object) -> Maxwell3dApp: ...


class DefaultMaxwell3dAppFactory:
    @property
    def pyaedt_version(self) -> str:
        try:
            return version("pyaedt")
        except PackageNotFoundError:
            return "not-installed"

    def create(self, **kwargs: object) -> Maxwell3dApp:
        from ansys.aedt.core import Maxwell3d

        return cast(Maxwell3dApp, Maxwell3d(**kwargs))


def _stage_units(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    app.modeler.model_units = "meter"
    return "Model units set to meter."


def _stage_materials(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    spec = plan.core.material
    material = app.materials.add_material(spec.name)
    material.permeability = spec.relative_permeability
    material.conductivity = spec.conductivity_s_per_m
    return f"Material {spec.name} created (draft={spec.draft})."


def _stage_core(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    data = polyline_data(plan.core.profile, closed=True)
    app.modeler.create_polyline(
        points=[list(point) for point in data.points],
        segment_type=list(data.kinds),
        name=plan.core.name,
        cover_surface=True,
        close_surface=False,
    )
    app.modeler.sweep_around_axis(plan.core.name, axis="Z", sweep_angle=360)
    app.assign_material(plan.core.name, plan.core.material.name)
    return f"Core {plan.core.name} revolved and assigned {plan.core.material.name}."


def _stage_windings(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for turn in group.turns:
            data = polyline_data(turn.segments, closed=True)
            app.modeler.create_polyline(
                points=[list(point) for point in data.points],
                segment_type=list(data.kinds),
                name=turn.name,
                material=COPPER_MATERIAL,
                xsection_type="Circle",
                xsection_width=turn.bare_diameter_m,
                xsection_num_seg=0,
            )
            count += 1
    return f"{count} turn conductors created."


def _stage_terminals(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for turn in group.turns:
            disk = turn.terminal.disk
            radial = math.hypot(disk.center.x, disk.center.y)
            app.modeler.create_circle(
                orientation="YZ",
                origin=[round(radial, 9), 0.0, disk.center.z],
                radius=disk.radius_m,
                name=turn.terminal.name,
            )
            app.modeler.rotate(turn.terminal.name, axis="Z", angle=disk.station_deg)
            count += 1
    return f"{count} terminal sheets created."


def _stage_excitations(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    for group in plan.windings:
        coil_names: list[str] = []
        for turn in group.turns:
            coil = f"{turn.name}_Coil"
            app.assign_coil(
                turn.terminal.name,
                conductors_number=1,
                polarity=turn.terminal.polarity.value,
                name=coil,
            )
            coil_names.append(coil)
        app.assign_winding(
            assignment=None,
            winding_type="Current",
            is_solid=group.is_solid,
            current=group.current_peak_a,
            phase=group.phase_deg,
            name=group.name,
        )
        app.add_winding_coils(assignment=group.name, coils=coil_names)
    return f"{len(plan.windings)} windings excited."


def _stage_eddy(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    solid = [t.name for g in plan.windings if g.is_solid for t in g.turns]
    stranded = [t.name for g in plan.windings if not g.is_solid for t in g.turns]
    if solid:
        app.eddy_effects_on(solid, enable_eddy_effects=True)
    if stranded:
        app.eddy_effects_on(stranded, enable_eddy_effects=False)
    return f"Eddy effects: {len(solid)} solid on, {len(stranded)} stranded off."


def _stage_region(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    pad = plan.region.padding_percent
    app.modeler.create_air_region(pad, pad, pad, pad, pad, pad)
    return f"Air region with {pad:g}% padding."


def _stage_mesh(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    conductors = [t.name for g in plan.windings for t in g.turns]
    app.mesh.assign_length_mesh(
        conductors, maximum_length=plan.mesh.conductor_max_length_m, name="ConductorLength"
    )
    app.mesh.assign_length_mesh(
        [plan.core.name], maximum_length=plan.mesh.core_max_length_m, name="CoreLength"
    )
    return "Length-based mesh restrictions assigned."


def _stage_setup(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    setup = app.create_setup(name=plan.setup.name)
    setup.props["Frequency"] = f"{plan.setup.frequency_hz:g}Hz"
    setup.props["MaximumPasses"] = plan.setup.maximum_passes
    setup.props["PercentError"] = plan.setup.percent_error
    setup.update()
    return f"Setup {plan.setup.name} at {plan.setup.frequency_hz:g} Hz."


def _stage_matrix(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    from ansys.aedt.core.modules.boundary.maxwell_boundary import (
        MatrixACMagnetic,
        SourceACMagnetic,
    )

    sources = [SourceACMagnetic(name=g.name) for g in plan.windings]
    schema = MatrixACMagnetic(signal_sources=sources, matrix_name=plan.matrix_name)
    app.assign_matrix(schema)
    return f"Matrix {plan.matrix_name} over {len(plan.windings)} windings."


def _stage_reports(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    for report in plan.reports:
        app.post.create_report(expressions=[report.expression], plot_name=report.name)
    return f"{len(plan.reports)} reports requested."


def _stage_validate(app: Maxwell3dApp, plan: Maxwell3dDesignPlan) -> str:
    if app.validate_simple() != 1:
        raise RuntimeError("Design validation failed.")
    return "Design validation passed."


_STAGES: tuple[tuple[str, Any], ...] = (
    ("units", _stage_units),
    ("materials", _stage_materials),
    ("core", _stage_core),
    ("windings", _stage_windings),
    ("terminals", _stage_terminals),
    ("excitations", _stage_excitations),
    ("eddy", _stage_eddy),
    ("region", _stage_region),
    ("mesh", _stage_mesh),
    ("setup", _stage_setup),
    ("matrix", _stage_matrix),
    ("reports", _stage_reports),
    ("validate", _stage_validate),
)


class PyaedtMaxwell3dExporter:
    """Executes a Maxwell3dDesignPlan as named stages; never reports a partial design."""

    def __init__(self, app_factory: Maxwell3dAppFactory | None = None) -> None:
        self._factory = DefaultMaxwell3dAppFactory() if app_factory is None else app_factory

    def export(self, request: Maxwell3dExportRequest) -> Maxwell3dExportResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        project_path = request.output_directory / f"{request.project_name}.aedt"
        project_path.unlink(missing_ok=True)
        plan = request.plan
        stages: list[StageRecord] = []

        def result() -> Maxwell3dExportResult:
            return Maxwell3dExportResult(
                project_path=project_path,
                design_name=plan.design_name,
                pyaedt_version=self._factory.pyaedt_version,
                stages=tuple(stages),
            )

        try:
            app = self._factory.create(
                project=str(project_path),
                design=plan.design_name,
                solution_type=plan.solution_type,
                version=str(request.release),
                non_graphical=request.non_graphical,
                new_desktop=True,
                close_on_exit=False,
                student_version=request.edition.value == "student",
            )
        except Exception as error:  # noqa: BLE001 - stage boundary converts to record
            stages.append(StageRecord(name="launch", succeeded=False, message=str(error)))
            return result()
        stages.append(
            StageRecord(
                name="launch",
                succeeded=True,
                message=f"Maxwell 3D design {plan.design_name!r} opened.",
            )
        )
        try:
            for name, stage in _STAGES:
                try:
                    message = stage(app, plan)
                except Exception as error:  # noqa: BLE001 - stage boundary
                    stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                    return result()
                stages.append(StageRecord(name=name, succeeded=True, message=message))
            try:
                saved = bool(app.save_project(str(project_path)))
                stages.append(
                    StageRecord(
                        name="save",
                        succeeded=saved,
                        message="Project saved." if saved else "save_project returned False.",
                    )
                )
            except Exception as error:  # noqa: BLE001 - stage boundary
                stages.append(StageRecord(name="save", succeeded=False, message=str(error)))
        finally:
            app.release_desktop(close_projects=True, close_desktop=True)
        return result()
