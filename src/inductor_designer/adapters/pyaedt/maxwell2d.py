from __future__ import annotations

import math
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Protocol, cast

from inductor_designer.adapters.pyaedt.desktop_cleanup import (
    release_orphaned_desktops,
)
from inductor_designer.adapters.pyaedt.field_reader import (
    CURRENT_DENSITY_QUANTITY,
    FLUX_DENSITY_QUANTITY,
    EvaluatedArea,
    read_field_areas,
)
from inductor_designer.adapters.pyaedt.live_app import LiveAppExtraction
from inductor_designer.adapters.pyaedt.material_props import (
    apply_steinmetz_unit_fix,
    enable_core_loss,
)
from inductor_designer.adapters.pyaedt.result_reader import read_scalar_results
from inductor_designer.adapters.pyaedt.solve_watch import analyze_watched
from inductor_designer.adapters.pyaedt.stage_progress import (
    record_cancellation as _record_cancellation,
)
from inductor_designer.application.ports.maxwell2d_exporter import Maxwell2dExportRequest
from inductor_designer.application.ports.maxwell_exporter import (
    MaxwellExportResult,
    StageRecord,
)
from inductor_designer.simulation.maxwell2d_plan import Maxwell2dDesignPlan
from inductor_designer.simulation.maxwell_plan import (
    COPPER_MATERIAL,
    INITIAL_MESH_SLIDER_LEVEL,
)
from inductor_designer.simulation.raw_results import RawScalarResults
from inductor_designer.simulation.run_control import (
    CancellationToken,
    RunCancelled,
    StagePhase,
)
from inductor_designer.simulation.run_control import (
    emit_stage_event as _emit,
)
from inductor_designer.simulation.run_control import (
    is_cancelled as _cancelled,
)


def _results_message(raw: RawScalarResults) -> str:
    if raw.diagnostics:
        return f"Result extraction incomplete: {'; '.join(raw.diagnostics)}"
    return (
        f"{len(raw.windings)} winding result(s), {len(raw.matrices)} matrix/matrices, "
        f"convergence {'read' if raw.convergence is not None else 'not exposed'}."
    )


class Maxwell2dApp(Protocol):
    modeler: Any
    mesh: Any
    post: Any
    materials: Any
    model_depth: Any

    def assign_material(self, assignment: Any, material: str) -> Any: ...

    def set_core_losses(
        self, assignment: Any, core_loss_on_field: bool = ...
    ) -> Any: ...

    def assign_coil(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_winding(self, assignment: Any = ..., **kwargs: Any) -> Any: ...

    def add_winding_coils(self, assignment: Any, coils: Any) -> Any: ...

    def eddy_effects_on(self, assignment: Any, **kwargs: Any) -> Any: ...

    def create_setup(self, name: str) -> Any: ...

    def assign_matrix(self, assignment: Any, **kwargs: Any) -> Any: ...

    def assign_balloon(self, assignment: Any, **kwargs: Any) -> Any: ...

    def validate_simple(self, log_file: str | None = None) -> int: ...

    def analyze_setup(self, name: str, *, blocking: bool = True) -> bool: ...

    are_there_simulations_running: Any

    def stop_simulations(self, clean_stop: bool = True) -> Any: ...

    def setup_convergence(self, name: str) -> str: ...

    def solution_values(self, expressions: tuple[str, ...]) -> Any: ...

    def field_value(
        self,
        quantity: str,
        scalar_function: str,
        object_name: str,
        object_type: str,
    ) -> float: ...

    def convergence_rows(self, name: str) -> tuple[tuple[int, float], ...]: ...

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

        try:
            return cast(Maxwell2dApp, LiveAppExtraction(Maxwell2d(**kwargs)))
        except Exception:
            # The desktop is spawned before the application object finishes
            # initialising, and `close_on_exit=False` keeps it alive, so a
            # failure here leaves a headless ansysedt.exe behind that has no
            # owner. The next launch then finds two gRPC sessions, attaches to
            # the wrong one, and dies with
            # `'NoneType' object has no attribute 'GetName'` -- which is how
            # one orphan cost two runs on 2026-08-14.
            release_orphaned_desktops()
            raise


def _stage_units(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    app.modeler.model_units = "meter"
    return "Model units set to meter."


def _stage_materials(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    spec = plan.core.material
    material = app.materials.add_material(spec.name)
    material.permeability = (
        [[h, b] for b, h in spec.bh_curve]
        if spec.bh_curve
        else spec.relative_permeability
    )
    material.conductivity = spec.conductivity_s_per_m
    if spec.mass_density_kg_per_m3 is not None:
        material.mass_density = spec.mass_density_kg_per_m3
    if spec.steinmetz is not None:
        accepted = material.set_power_ferrite_coreloss(
            cm=spec.steinmetz.k,
            x=spec.steinmetz.alpha,
            y=spec.steinmetz.beta,
        )
        if not accepted:
            raise RuntimeError("PyAEDT rejected the ferrite core-loss model.")
        apply_steinmetz_unit_fix(material, spec.steinmetz)
    return f"Material {spec.name} created (draft={spec.draft})."


def _stage_core(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    bore = f"{plan.core.name}_Bore"
    app.modeler.create_circle(
        origin=[0.0, 0.0, 0.0], radius=plan.core.r_outer_m, name=plan.core.name
    )
    app.modeler.create_circle(origin=[0.0, 0.0, 0.0], radius=plan.core.r_inner_m, name=bore)
    app.modeler.subtract(plan.core.name, bore, keep_originals=False)
    app.assign_material(plan.core.name, plan.core.material.name)
    return f"Annular core {plan.core.name} created." + enable_core_loss(
        app, plan.core.name, plan.core.material, plan.solution_type
    )


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
    # Maxwell 2D exposes neither the TAU mesher nor the curvilinear switch that
    # the 3D adapter relies on, so only the surface-approximation slider carries
    # over. 2D never links a DC solution into an AC one, so it does not hit the
    # mapping failure those 3D settings work around.
    app.mesh.assign_initial_mesh_from_slider(level=INITIAL_MESH_SLIDER_LEVEL)
    conductors = [c.name for g in plan.windings for c in g.conductors]
    app.mesh.assign_length_mesh(
        conductors, maximum_length=plan.mesh.conductor_max_length_m, name="ConductorLength"
    )
    app.mesh.assign_length_mesh(
        [plan.core.name], maximum_length=plan.mesh.core_max_length_m, name="CoreLength"
    )
    # TAU's 2D surface mesher refuses to mesh at all in meter model units once a
    # feature (here, the conductor-to-core clearance) drops to tens of microns
    # -- e.g. 4.7e-5 in meter units is below its working tolerance, and it fails
    # in under a second, before producing a single element. The same geometry
    # meshes cleanly once the *model units* read millimeter, because all prior
    # geometry and mesh lengths were already stored with an explicit 'meter'
    # suffix (set while app.modeler.model_units was "meter" in _stage_units), so
    # this only changes the mesher's tolerance, not the model's physical size.
    # Verified live on AEDT 2025.2, 2026-08-12; see GitHub issue #14.
    app.modeler.model_units = "mm"
    return "Length-based mesh restrictions assigned; model units set to mm for TAU meshing."


# AEDT's own default (1) accepts the first pass as converged even if nothing
# has been refined yet. 2D carries none of the DC-bias mesh-mapping fragility
# that keeps Maxwell 3D pinned to one adaptive pass (see
# docs/development/dc-bias-solve-limitation.md), so there is no regression
# risk in raising the floor here.
MINIMUM_PASSES_2D = 3


def _stage_setup(app: Maxwell2dApp, plan: Maxwell2dDesignPlan) -> str:
    # Non-graphical AEDT rejects design-settings writes (model_depth) on an
    # empty design, so depth is set here, once geometry/region/boundary exist.
    app.model_depth = f"{plan.model_depth_m:g}meter"
    setup = app.create_setup(name=plan.setup.name)
    setup.props["Frequency"] = f"{plan.setup.frequency_hz:g}Hz"
    setup.props["MaximumPasses"] = plan.setup.maximum_passes
    setup.props["MinimumPasses"] = MINIMUM_PASSES_2D
    setup.props["PercentError"] = plan.setup.percent_error
    setup.update()
    return (
        f"Model depth {plan.model_depth_m:g} m; "
        f"setup {plan.setup.name} at {plan.setup.frequency_hz:g} Hz."
    )


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


def _stage_analyze(
    app: Maxwell2dApp,
    plan: Maxwell2dDesignPlan,
    cancellation: CancellationToken | None = None,
) -> str:
    analyze_watched(app, plan.setup.name, cancellation=cancellation)
    return f"Solved {plan.setup.name}: {app.setup_convergence(plan.setup.name)}."


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



def _with_field_regions(
    app: Maxwell2dApp,
    plan: Maxwell2dDesignPlan,
    raw: RawScalarResults,
) -> RawScalarResults:
    """2D integrates the evaluated regions directly: no cut planes, no sheets.

    The design forbids sections here, because in 2D the evaluated area is the
    region itself. Areas come from the plan geometry, so no extra solver call
    is needed to know what the mean divides by.
    """
    from dataclasses import replace

    core_area = math.pi * (plan.core.r_outer_m**2 - plan.core.r_inner_m**2)
    core_regions = (
        EvaluatedArea(
            name=plan.core.name,
            section_id="core.region",
            scope="core.region",
            area_m2=core_area,
        ),
    )
    conductor_regions = tuple(
        EvaluatedArea(
            name=conductor.name,
            section_id=f"{group.winding_id}.region",
            scope=f"winding.{group.winding_id}.region",
            area_m2=math.pi * conductor.radius_m**2,
        )
        for group in plan.windings
        for conductor in group.conductors[:1]
    )
    return replace(
        raw,
        flux_density_sections=read_field_areas(
            app, core_regions, FLUX_DENSITY_QUANTITY
        ),
        current_density_sections=read_field_areas(
            app, conductor_regions, CURRENT_DENSITY_QUANTITY
        ),
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
        raw_results: RawScalarResults | None = None

        def result() -> MaxwellExportResult:
            return MaxwellExportResult(
                project_path=project_path,
                design_name=plan.design_name,
                pyaedt_version=self._factory.pyaedt_version,
                stages=tuple(stages),
                raw_results=raw_results,
            )

        _emit(request.progress, "launch", StagePhase.STARTED, None)
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
            _emit(request.progress, "launch", StagePhase.FAILED, str(error))
            return result()
        launch_message = f"Maxwell 2D design {plan.design_name!r} opened."
        stages.append(
            StageRecord(name="launch", succeeded=True, message=launch_message)
        )
        _emit(request.progress, "launch", StagePhase.SUCCEEDED, launch_message)
        try:
            cancelled_before: str | None = None
            for name, stage in _STAGES_2D:
                if _cancelled(request.cancellation):
                    cancelled_before = name
                    break
                _emit(request.progress, name, StagePhase.STARTED, None)
                try:
                    message = stage(app, plan)
                except Exception as error:  # noqa: BLE001 - stage boundary
                    stages.append(StageRecord(name=name, succeeded=False, message=str(error)))
                    _emit(request.progress, name, StagePhase.FAILED, str(error))
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
                _emit(request.progress, name, StagePhase.SUCCEEDED, message)
            # The save runs even after cancellation: an interrupted run still
            # keeps whatever the design reached, it just never claims success.
            _emit(request.progress, "save", StagePhase.STARTED, None)
            try:
                saved = bool(app.save_project(str(project_path)))
                save_message = "Project saved." if saved else "save_project returned False."
                stages.append(
                    StageRecord(name="save", succeeded=saved, message=save_message)
                )
                _emit(
                    request.progress,
                    "save",
                    StagePhase.SUCCEEDED if saved else StagePhase.FAILED,
                    save_message,
                )
            except Exception as error:  # noqa: BLE001 - stage boundary
                stages.append(StageRecord(name="save", succeeded=False, message=str(error)))
                _emit(request.progress, "save", StagePhase.FAILED, str(error))
                return result()
            if cancelled_before is None and request.solve:
                if _cancelled(request.cancellation):
                    cancelled_before = "analyze"
                else:
                    _emit(request.progress, "analyze", StagePhase.STARTED, None)
                    try:
                        message = _stage_analyze(app, plan, request.cancellation)
                    except RunCancelled:
                        # The solve itself was stopped, so there is nothing to
                        # read; the run ends cancelled, not failed.
                        cancelled_before = "analyze"
                    except Exception as error:  # noqa: BLE001 - stage boundary
                        stages.append(
                            StageRecord(name="analyze", succeeded=False, message=str(error))
                        )
                        _emit(request.progress, "analyze", StagePhase.FAILED, str(error))
                        return result()
                    else:
                        stages.append(
                            StageRecord(name="analyze", succeeded=True, message=message)
                        )
                        _emit(request.progress, "analyze", StagePhase.SUCCEEDED, message)
                        # Extraction never fails a solved run: a read error rides
                        # along as a diagnostic and normalizes to unavailable.
                        _emit(request.progress, "results", StagePhase.STARTED, None)
                        raw_results = read_scalar_results(
                            app,
                            matrix_name=plan.matrix_name,
                            winding_names=tuple(group.name for group in plan.windings),
                            setup_name=plan.setup.name,
                            frequency_hz=plan.setup.frequency_hz,
                        )
                        raw_results = _with_field_regions(app, plan, raw_results)
                        results_message = _results_message(raw_results)
                        stages.append(
                            StageRecord(
                                name="results", succeeded=True, message=results_message
                            )
                        )
                        _emit(
                            request.progress,
                            "results",
                            StagePhase.SUCCEEDED,
                            results_message,
                        )
            if cancelled_before is not None:
                _record_cancellation(stages, request.progress, cancelled_before)
        finally:
            app.release_desktop(close_projects=True, close_desktop=True)
        return result()
