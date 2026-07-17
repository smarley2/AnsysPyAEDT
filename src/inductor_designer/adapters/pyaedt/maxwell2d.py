from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, cast

from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExportRequest
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import COPPER_MATERIAL


class Maxwell2dApp(Protocol):
    modeler: Any
    mesh: Any
    post: Any
    materials: Any
    model_depth: Any

    def assign_material(self, assignment: Any, material: str) -> Any: ...

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_winding(self, assignment: Any = ..., **kwargs: Any) -> Any: ...

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any: ...

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any: ...

    def create_setup(self, name: str) -> Any: ...

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_balloon(self, assignment: Any, **kwargs: Any) -> Any: ...

    def validate_simple(self, log_file: str | None = None) -> int: ...

    def save_project(self, path: str) -> bool: ...

    def release_desktop(self, close_projects: bool, close_desktop: bool) -> None: ...


class Maxwell2dAppFactory(Protocol):
    pyaedt_version: str

    def create(self, **kwargs: object) -> Maxwell2dApp: ...


class DefaultMaxwell2dAppFactory:
    @property
    def pyaedt_version(self) -> str:
        try:
            return version("pyaedt")
        except PackageNotFoundError:
            return "not-installed"

    def create(self, **kwargs: object) -> Maxwell2dApp:
        from ansys.aedt.core import Maxwell2d

        return cast(Maxwell2dApp, Maxwell2d(**kwargs))


def _stage_units(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    app.modeler.model_units = "meter"
    app.model_depth = f"{plan.model_depth_m:g}meter"
    return f"Units meter; model depth {plan.model_depth_m:g} m."


def _stage_materials(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    spec = plan.core.material
    material = app.materials.add_material(spec.name)
    material.permeability = spec.relative_permeability
    material.conductivity = spec.conductivity_s_per_m
    return f"Material {spec.name} created (draft={spec.draft})."


def _stage_core(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    bore = f"{plan.core.name}_Bore"
    app.modeler.create_circle(
        origin=[0.0, 0.0, 0.0], radius=plan.core.r_outer_m, name=plan.core.name
    )
    app.modeler.create_circle(origin=[0.0, 0.0, 0.0], radius=plan.core.r_inner_m, name=bore)
    app.modeler.subtract(plan.core.name, bore, keep_originals=False)
    app.assign_material(plan.core.name, plan.core.material.name)
    return f"Annular core {plan.core.name} created."


def _stage_conductors(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    count = 0
    for group in plan.windings:
        for conductor in group.conductors:
            app.modeler.create_circle(
                origin=[conductor.x_m, conductor.y_m, 0.0],
                radius=conductor.radius_m,
                name=conductor.name,
                material=COPPER_MATERIAL,
            )
            count += 1
    return f"{count} conductor regions created."


def _stage_excitations(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    for group in plan.windings:
        coil_names: list[str] = []
        for conductor in group.conductors:
            coil = f"{conductor.name}_Coil"
            app.assign_coil(
                conductor.name,
                conductors_number=1,
                polarity=conductor.polarity.value,
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


def _stage_eddy(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    solid = [c.name for g in plan.windings if g.is_solid for c in g.conductors]
    stranded = [c.name for g in plan.windings if not g.is_solid for c in g.conductors]
    if solid:
        app.eddy_effects_on(solid, enable_eddy_effects=True)
    if stranded:
        app.eddy_effects_on(stranded, enable_eddy_effects=False)
    return f"Eddy effects: {len(solid)} solid on, {len(stranded)} stranded off."


def _stage_region(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    pad = plan.region.padding_percent
    region = app.modeler.create_region(pad_value=pad, pad_type="Percentage Offset")
    if not region:
        raise RuntimeError("create_region returned no region object.")
    balloon = app.assign_balloon(region.edges, boundary="Balloon")
    if not balloon:
        raise RuntimeError("assign_balloon returned no boundary object.")
    return f"Air region with {pad:g}% padding; balloon boundary on region edges."


def _stage_mesh(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    conductors = [c.name for g in plan.windings for c in g.conductors]
    app.mesh.assign_length_mesh(
        conductors, maximum_length=plan.mesh.conductor_max_length_m, name="ConductorLength"
    )
    app.mesh.assign_length_mesh(
        [plan.core.name], maximum_length=plan.mesh.core_max_length_m, name="CoreLength"
    )
    return "Length-based mesh restrictions assigned."


def _stage_setup(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    setup = app.create_setup(name=plan.setup.name)
    setup.props["Frequency"] = f"{plan.setup.frequency_hz:g}Hz"
    setup.props["MaximumPasses"] = plan.setup.maximum_passes
    setup.props["PercentError"] = plan.setup.percent_error
    setup.update()
    return f"Setup {plan.setup.name} at {plan.setup.frequency_hz:g} Hz."


def _stage_matrix(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    from ansys.aedt.core.modules.boundary.maxwell_boundary import (
        MatrixACMagnetic,
        SourceACMagnetic,
    )

    sources = [SourceACMagnetic(name=g.name) for g in plan.windings]
    schema = MatrixACMagnetic(signal_sources=sources, matrix_name=plan.matrix_name)
    app.assign_matrix(schema)
    return f"Matrix {plan.matrix_name} over {len(plan.windings)} windings."


def _stage_reports(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    for report in plan.reports:
        app.post.create_report(expressions=[report.expression], plot_name=report.name)
    return f"{len(plan.reports)} reports requested."


def _stage_validate(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    if app.validate_simple() != 1:
        raise RuntimeError("Design validation failed.")
    return "Design validation passed."


_STAGES_2D: tuple[tuple[str, Any], ...] = (
    ("units", _stage_units),
    ("materials", _stage_materials),
    ("core", _stage_core),
    ("conductors", _stage_conductors),
    ("excitations", _stage_excitations),
    ("eddy", _stage_eddy),
    ("region", _stage_region),
    ("mesh", _stage_mesh),
    ("setup", _stage_setup),
    ("matrix", _stage_matrix),
    ("reports", _stage_reports),
    ("validate", _stage_validate),
)


class PyaedtMaxwell2dExporter:
    """Executes a Maxwell2dDesignPlan as named stages; never reports a partial design."""

    def __init__(self, app_factory: Maxwell2dAppFactory | None = None) -> None:
        self._factory = DefaultMaxwell2dAppFactory() if app_factory is None else app_factory

    def export(self, request: Maxwell2dExportRequest) -> MaxwellExportResult:
        request.output_directory.mkdir(parents=True, exist_ok=True)
        project_path = request.output_directory / f"{request.project_name}.aedt"
        project_path.unlink(missing_ok=True)
        plan = request.plan
        stages: list[StageRecord] = []

        def result() -> MaxwellExportResult:
            return MaxwellExportResult(
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
                message=f"Maxwell 2D design {plan.design_name!r} opened.",
            )
        )
        try:
            for name, stage in _STAGES_2D:
                try:
                    message = stage(app, plan)
                except Exception as error:  # noqa: BLE001 - stage boundary
                    stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                    try:
                        app.save_project(str(project_path))
                        stages.append(
                            StageRecord(
                                name="save",
                                succeeded=True,
                                message="Diagnostic save after failed stage.",
                            )
                        )
                    except Exception as save_error:  # noqa: BLE001 - stage boundary
                        stages.append(
                            StageRecord(name="save", succeeded=False, message=str(save_error))
                        )
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
